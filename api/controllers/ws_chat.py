import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api import state
from api.bus import EventBus
from api.producers.chat_producer import build_chat_message, publish_chat_message

router = APIRouter(tags=["chat"])
_logger = logging.getLogger("api.controllers.ws_chat")


@router.websocket("/ws/chat/{channel}")
async def websocket_chat(websocket: WebSocket, channel: str) -> None:
    await websocket.accept()

    client_ip = websocket.headers.get("x-forwarded-for", websocket.client.host)
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    sender = f"{client_ip}:{id(websocket)}"

    pubsub = state.redis_client.pubsub()
    await pubsub.subscribe(EventBus.chat_channel(channel))

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
                await asyncio.sleep(25)
                await websocket.send_text(json.dumps({"type": "ping"}))
        except Exception:
            pass

    update_task = asyncio.create_task(send_updates())
    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        while True:
            raw = await websocket.receive_text()
            _logger.debug("[ws_chat] Received raw message: %s", raw[:500] if raw else "<empty>")
            try:
                payload = json.loads(raw)
                text = payload.get("text")
                if not text:
                    _logger.debug("[ws_chat] No text in payload, skipping")
                    continue
            except Exception as e:
                _logger.debug("[ws_chat] Failed to parse payload: %s", e)
                continue
            _logger.info("[ws_chat] Human message from %s on channel=%s: %s", sender, channel, text[:200] if text else "<empty>")
            event = build_chat_message(channel=channel, sender=sender, text=text)
            _logger.debug("[ws_chat] Built event: %s", event)
            await publish_chat_message(state.event_bus, channel, event)
            _logger.debug("[ws_chat] Published message to channel=%s", channel)
    except WebSocketDisconnect:
        _logger.debug("[ws_chat] WebSocket disconnected for %s", sender)
    finally:
        update_task.cancel()
        heartbeat_task.cancel()

        # Cleanup pubsub with error handling
        try:
            await asyncio.wait_for(
                pubsub.unsubscribe(EventBus.chat_channel(channel)), timeout=2.0
            )
        except asyncio.TimeoutError:
            _logger.warning("Timeout unsubscribing from chat channel %s", channel)
        except Exception as e:
            _logger.warning("Error unsubscribing from chat channel %s: %s", channel, e)

        try:
            if hasattr(pubsub, "aclose"):
                await asyncio.wait_for(pubsub.aclose(), timeout=2.0)
            else:
                await asyncio.wait_for(pubsub.close(), timeout=2.0)
        except asyncio.TimeoutError:
            _logger.warning("Timeout closing pubsub connection for channel %s", channel)
        except Exception as e:
            _logger.warning("Error closing pubsub for channel %s: %s", channel, e)
