"""
Redis Pub/Sub bridge for cross-process WebSocket notifications.

The Celery worker runs in a separate process and cannot access FastAPI's
in-memory ConnectionManager. This module provides:

  Publisher side (Celery worker):  publish_chunk_done()
  Subscriber side (FastAPI):       start_redis_subscriber() background task

Flow:
  Worker → Redis channel "ws_events" → FastAPI lifespan task → WS clients
"""
import asyncio
import json
import logging
import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

CHANNEL = "ws_events"


# ── Publisher (called from Celery worker, sync context) ───────────────────────

def publish_event_sync(event: dict) -> None:
    """
    Synchronously publish a WS event to Redis.
    Called from the Celery task (non-async context).
    """
    import redis as sync_redis
    try:
        r = sync_redis.from_url(settings.redis_url, decode_responses=True)
        r.publish(CHANNEL, json.dumps(event))
        r.close()
        logger.info(f"[Redis pub] Published: {event}")
    except Exception as e:
        logger.error(f"[Redis pub] Failed to publish event: {e}")


# ── Subscriber (runs as background task inside FastAPI) ───────────────────────

async def start_redis_subscriber(manager) -> None:
    """
    Long-running coroutine that subscribes to Redis ws_events channel
    and forwards events to the in-process WebSocket manager.
    
    Should be started as an asyncio task during app lifespan.
    """
    while True:
        try:
            r = aioredis.from_url(settings.redis_url, decode_responses=True)
            pubsub = r.pubsub()
            await pubsub.subscribe(CHANNEL)
            logger.info(f"[Redis sub] Subscribed to channel: {CHANNEL}")

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    event = json.loads(message["data"])
                    session_id = event.get("session_id")
                    if session_id:
                        await manager.broadcast(session_id, event)
                        logger.info(f"[Redis sub] Forwarded event to WS: {event}")
                except Exception as e:
                    logger.error(f"[Redis sub] Failed to process event: {e}")

        except Exception as e:
            logger.warning(f"[Redis sub] Connection lost ({e}), retrying in 3s...")
            await asyncio.sleep(3)
