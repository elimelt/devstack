"""Internal API entrypoint - not publicly accessible, only via authenticated homepage."""

import logging
import os

import redis.asyncio as redis

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
)
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import BlockingConnectionPool as RedisConnectionPool

from api import db, state
from api.agents.augment_agent import start_augment_agent
from api.bus import EventBus
from api.controllers.augment_chat import router as augment_chat_router
from api.controllers.chat_admin import router as chat_admin_router
from api.controllers.health import router as health_router
from api.redis_debug import wrap_redis_client

app = FastAPI(title="DevStack Internal API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

redis_client = None
event_bus: EventBus | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global redis_client, event_bus
    stop_event: asyncio.Event | None = None
    agent_tasks: list[asyncio.Task] = []

    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_password = os.getenv("REDIS_PASSWORD", "")

    max_redis_conns = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
    pool_timeout = float(os.getenv("REDIS_POOL_TIMEOUT_SEC", "5"))
    redis_pool = RedisConnectionPool(
        host=redis_host,
        port=redis_port,
        password=redis_password if redis_password else None,
        max_connections=max_redis_conns,
        timeout=pool_timeout,
    )
    candidate_client = redis.Redis(connection_pool=redis_pool, decode_responses=True)
    if hasattr(candidate_client, "__await__"):
        redis_client = await candidate_client
    else:
        redis_client = candidate_client
    if os.getenv("REDIS_DEBUG", "0") == "1":
        logging.getLogger("api.redis").setLevel(logging.DEBUG)
        redis_logger = logging.getLogger("api.redis")
        redis_client = wrap_redis_client(redis_client, redis_logger)
    event_bus = EventBus(redis_client)

    state.redis_client = redis_client
    state.event_bus = event_bus

    enable_db = os.getenv("ENABLE_CHAT_DB", "0") == "1"
    if enable_db:
        try:
            await db.init_pool()
        except Exception:
            pass

    # Start Augment agent
    enable_agent = os.getenv("ENABLE_AUGMENT_AGENT", "1") == "1"
    if enable_agent:
        stop_event = asyncio.Event()
        agent_tasks = await start_augment_agent(stop_event)

    try:
        yield
    finally:
        # Stop agent tasks
        if agent_tasks and stop_event:
            stop_event.set()
            try:
                await asyncio.wait_for(
                    asyncio.gather(*agent_tasks, return_exceptions=True), timeout=5
                )
            except Exception:
                for t in agent_tasks:
                    t.cancel()

        if enable_db:
            try:
                await db.close_pool()
            except Exception:
                pass
        if redis_client:
            aclose = getattr(redis_client, "aclose", None)
            if callable(aclose):
                await aclose()
            else:
                close = getattr(redis_client, "close", None)
                if callable(close):
                    close()
        state.redis_client = None
        state.event_bus = None


app.router.lifespan_context = lifespan

app.include_router(health_router)
app.include_router(augment_chat_router)
app.include_router(chat_admin_router)

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
