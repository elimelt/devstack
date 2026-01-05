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
from api.batch.notes_sync_scheduler import start_notes_sync_scheduler
from api.bus import EventBus
from api.controllers.analytics_clicks_write import router as analytics_clicks_write_router
from api.controllers.augment_chat import router as augment_chat_router
from api.controllers.cache_write import router as cache_write_router
from api.controllers.chat_admin import router as chat_admin_router
from api.controllers.health import router as health_router
from api.controllers.notes_write import router as notes_write_router
from api.controllers.notes_search_write import router as notes_search_write_router
from api.controllers.when2meet_write import router as when2meet_write_router
from api.redis_debug import wrap_redis_client

app = FastAPI(
    title="DevStack Internal API",
    version="1.0.0",
    root_path="/api",
)

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
    sync_tasks: list[asyncio.Task] = []

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

    enable_agent = os.getenv("ENABLE_AUGMENT_AGENT", "1") == "1"
    if enable_agent:
        stop_event = asyncio.Event()
        agent_tasks = await start_augment_agent(stop_event)

    enable_sync = os.getenv("NOTES_SYNC_ENABLED", "1") == "1"
    if enable_sync and enable_db:
        if stop_event is None:
            stop_event = asyncio.Event()
        sync_tasks = await start_notes_sync_scheduler(stop_event)

    try:
        yield
    finally:
        all_tasks = agent_tasks + sync_tasks
        if all_tasks and stop_event:
            stop_event.set()
            try:
                await asyncio.wait_for(
                    asyncio.gather(*all_tasks, return_exceptions=True), timeout=5
                )
            except Exception:
                for t in all_tasks:
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

app.include_router(cache_write_router)
app.include_router(analytics_clicks_write_router)
app.include_router(notes_write_router)
app.include_router(notes_search_write_router)
app.include_router(when2meet_write_router, prefix="/w2m")

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
