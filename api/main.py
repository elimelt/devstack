from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import redis.asyncio as redis
import geoip2.database
import json
import asyncio
from datetime import datetime
from typing import Set, Optional
import subprocess

class CacheValue(BaseModel):
    value: str
    ttl: Optional[int] = 3600

app = FastAPI(title="DevStack Public API", version="1.0.0")

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

redis_client = None
geoip_reader = None
active_connections: Set[WebSocket] = set()

@app.on_event("startup")
async def startup():
    global redis_client, geoip_reader
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_password = os.getenv("REDIS_PASSWORD", "")

    redis_client = await redis.Redis(
        host=redis_host,
        port=redis_port,
        password=redis_password if redis_password else None,
        decode_responses=True
    )

    geoip_db_path = os.getenv("GEOIP_DB_PATH", "/app/GeoLite2-City.mmdb")
    if os.path.exists(geoip_db_path):
        geoip_reader = geoip2.database.Reader(geoip_db_path)

@app.on_event("shutdown")
async def shutdown():
    if redis_client:
        await redis_client.close()
    if geoip_reader:
        geoip_reader.close()

def get_location(ip: str):
    default = {"country": "Unknown", "city": "Unknown", "lat": None, "lon": None}
    if not geoip_reader:
        return default

    try:
        response = geoip_reader.city(ip)
        return {
            "country": response.country.name or "Unknown",
            "city": response.city.name or "Unknown",
            "lat": response.location.latitude,
            "lon": response.location.longitude
        }
    except Exception:
        return default

@app.get("/health")
async def health():
    redis_status = "disconnected"
    if redis_client:
        try:
            await redis_client.ping()
            redis_status = "healthy"
        except Exception:
            redis_status = "unhealthy"

    return {"status": "ok", "redis": redis_status}

@app.get("/example")
async def example():
    return {
        "message": "Hello from DevStack API!",
        "timestamp": "2025-11-26T00:00:00Z",
        "status": "success"
    }

@app.get("/cache/{key}")
async def get_cache(key: str):
    if not redis_client:
        return {"error": "Redis not connected"}

    value = await redis_client.get(key)
    if value is None:
        return {"key": key, "value": None, "found": False}

    return {"key": key, "value": value, "found": True}

@app.post("/cache/{key}")
async def set_cache(key: str, data: CacheValue):
    if not redis_client:
        return {"error": "Redis not connected"}

    await redis_client.setex(key, data.ttl, data.value)
    return {"key": key, "value": data.value, "ttl": data.ttl, "success": True}

@app.get("/visitors")
async def get_visitors():
    if not redis_client:
        return {"error": "Redis not connected"}

    visitor_keys = await redis_client.keys("visitor:*")
    active_visitors = [
        json.loads(data)
        for key in visitor_keys
        if (data := await redis_client.get(key))
    ]

    visit_log = await redis_client.lrange("visit_log", 0, 99)
    visits = [json.loads(v) for v in visit_log]

    return {
        "active_count": len(active_visitors),
        "active_visitors": active_visitors,
        "recent_visits": visits
    }

@app.get("/system")
async def get_system():
    if redis_client:
        cached = await redis_client.get("system_stats")
        if cached:
            return json.loads(cached)

    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}|{{.Status}}|{{.Image}}"],
            capture_output=True,
            text=True,
            timeout=3
        )

        if result.returncode != 0:
            return {"error": "Failed to get container list"}

        container_info = {}
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|')
            if len(parts) == 3:
                name, status, image = parts
                container_info[name] = {"status": status, "image": image}

        container_names = list(container_info.keys())

        stats_map = {}
        if container_names:
            stats_result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}"] + container_names,
                capture_output=True,
                text=True,
                timeout=5
            )

            if stats_result.returncode == 0 and stats_result.stdout:
                for line in stats_result.stdout.strip().split('\n'):
                    if not line:
                        continue
                    parts = line.split('|')
                    if len(parts) == 4:
                        try:
                            name = parts[0]
                            cpu_percent = float(parts[1].replace('%', ''))
                            mem_usage = parts[2].split('/')[0].strip()

                            memory_mb = float(mem_usage.replace('MiB', ''))
                            if 'GiB' in mem_usage:
                                memory_mb = float(mem_usage.replace('GiB', '')) * 1024

                            memory_percent = float(parts[3].replace('%', ''))

                            stats_map[name] = {
                                "cpu_percent": round(cpu_percent, 2),
                                "memory_mb": round(memory_mb, 2),
                                "memory_percent": round(memory_percent, 2),
                            }
                        except Exception:
                            pass

        services = []
        for name in container_names:
            info = container_info.get(name, {})
            stats = stats_map.get(name, {"cpu_percent": 0.0, "memory_mb": 0.0, "memory_percent": 0.0})

            services.append({
                "name": name,
                "status": info.get("status", "unknown"),
                "image": info.get("image", "unknown"),
                **stats
            })

        response = {
            "total_containers": len(services),
            "services": sorted(services, key=lambda x: x['name'])
        }

        if redis_client:
            await redis_client.setex("system_stats", 5, json.dumps(response))

        return response
    except subprocess.TimeoutExpired:
        return {"error": "Docker command timed out"}
    except Exception as e:
        return {"error": str(e)}

@app.websocket("/ws/visitors")
async def websocket_visitors(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)

    client_ip = websocket.headers.get("x-forwarded-for", websocket.client.host)
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    location = get_location(client_ip)

    visitor_id = f"visitor:{client_ip}:{id(websocket)}"
    visitor_data = {
        "ip": client_ip,
        "location": location,
        "connected_at": datetime.utcnow().isoformat()
    }

    await redis_client.setex(visitor_id, 30, json.dumps(visitor_data))

    visit_entry = {
        "ip": client_ip,
        "location": location,
        "timestamp": datetime.utcnow().isoformat()
    }
    await redis_client.lpush("visit_log", json.dumps(visit_entry))
    await redis_client.ltrim("visit_log", 0, 999)

    await redis_client.publish("visitor_updates", json.dumps({
        "type": "join",
        "visitor": visitor_data
    }))

    pubsub = redis_client.pubsub()
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
                await redis_client.setex(visitor_id, 30, json.dumps(visitor_data))
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
    except WebSocketDisconnect:
        pass
    finally:
        update_task.cancel()
        heartbeat_task.cancel()
        active_connections.discard(websocket)
        await redis_client.delete(visitor_id)
        await pubsub.unsubscribe("visitor_updates")
        await pubsub.close()

        await redis_client.publish("visitor_updates", json.dumps({
            "type": "leave",
            "ip": client_ip
        }))

