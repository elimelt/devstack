import asyncio
import json
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api import db, state
from api.producers.visitor_producer import heartbeat as hb
from api.producers.visitor_producer import join_visitor, leave_visitor

router = APIRouter(tags=["visitors"])

_logger = logging.getLogger("api.ws.visitors")
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
    _handler.setFormatter(_fmt)
    _logger.addHandler(_handler)
_logger.setLevel(logging.INFO if os.getenv("WS_DEBUG", "0") == "1" else logging.WARNING)
_logger.propagate = False


async def _handle_analytics_batch(data: dict, client_ip: str) -> None:
    payload = data.get("payload", {})
    topic = payload.get("topic")
    events = payload.get("events", [])

    if topic != "clicks":
        _logger.warning(
            "analytics.batch unknown topic=%s ip=%s",
            topic,
            client_ip,
        )
        return

    if not events:
        return

    try:
        inserted = await db.insert_click_events(events, client_ip)
        _logger.info(
            "analytics.batch.clicks ip=%s count=%d inserted=%d",
            client_ip,
            len(events),
            inserted,
        )
    except Exception:
        _logger.exception("analytics.batch.clicks failed ip=%s", client_ip)


@router.websocket("/ws/visitors")
async def websocket_visitors(websocket: WebSocket) -> None:
    await websocket.accept()

    client_ip = websocket.headers.get("x-forwarded-for", websocket.client.host)
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    origin = websocket.headers.get("origin", "-")
    user_agent = websocket.headers.get("user-agent", "-")
    logger = _logger
    max_per_ip = int(os.getenv("WS_VISITORS_MAX_PER_IP", "50"))

    async with state.ws_visitors_lock:
        current = state.active_ws_visitors_by_ip.get(client_ip, 0) + 1
        state.active_ws_visitors_by_ip[client_ip] = current
        if current > max_per_ip:
            logger.info(
                "ws_visitors.reject ip=%s reason=per_ip_limit current=%s limit=%s origin=%s ua=%s",
                client_ip,
                current,
                max_per_ip,
                origin,
                user_agent,
            )
            await websocket.close(code=1008)
            state.active_ws_visitors_by_ip[client_ip] = current - 1
            return
    logger.info(
        "ws_visitors.accept ip=%s origin=%s ua=%s active_per_ip=%s",
        client_ip,
        origin,
        user_agent,
        state.active_ws_visitors_by_ip.get(client_ip),
    )

    visitor_id = f"visitor:{client_ip}:{id(websocket)}"

    visitor_data = await join_visitor(
        state.redis_client, state.event_bus, state.geoip_reader, client_ip, visitor_id
    )

    pubsub = state.redis_client.pubsub()
    await pubsub.subscribe("visitor_updates")

    async def send_updates():
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await websocket.send_text(message["data"])
        except Exception:
            pass

    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(10)
                await hb(state.redis_client, visitor_id, visitor_data)
                await websocket.send_text(json.dumps({"type": "ping"}))
        except Exception:
            pass

    update_task = asyncio.create_task(send_updates())
    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        while True:
            data = await websocket.receive_text()
            if data == "pong":
                continue

            try:
                msg = json.loads(data)
                if isinstance(msg, dict) and msg.get("type") == "analytics.batch":
                    asyncio.create_task(_handle_analytics_batch(msg, client_ip))
            except (json.JSONDecodeError, TypeError):
                pass
    except WebSocketDisconnect:
        pass
    finally:
        update_task.cancel()
        heartbeat_task.cancel()

        # Cleanup pubsub with error handling
        try:
            await asyncio.wait_for(pubsub.unsubscribe("visitor_updates"), timeout=2.0)
        except TimeoutError:
            _logger.warning("Timeout unsubscribing from visitor_updates")
        except Exception as e:
            _logger.warning("Error unsubscribing: %s", e)

        try:
            if hasattr(pubsub, "aclose"):
                await asyncio.wait_for(pubsub.aclose(), timeout=2.0)
            else:
                await asyncio.wait_for(pubsub.close(), timeout=2.0)
        except TimeoutError:
            _logger.warning("Timeout closing pubsub connection")
        except Exception as e:
            _logger.warning("Error closing pubsub: %s", e)

        # Continue with visitor leave
        try:
            await leave_visitor(state.redis_client, state.event_bus, client_ip, visitor_id)
        except Exception as e:
            _logger.warning("Error in leave_visitor: %s", e)

        async with state.ws_visitors_lock:
            if client_ip in state.active_ws_visitors_by_ip:
                state.active_ws_visitors_by_ip[client_ip] = max(
                    0, state.active_ws_visitors_by_ip[client_ip] - 1
                )
                if state.active_ws_visitors_by_ip[client_ip] == 0:
                    del state.active_ws_visitors_by_ip[client_ip]
        logger.info("ws_visitors.close ip=%s", client_ip)
