from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
import redis.asyncio as redis
import json
from app.config import settings

router = APIRouter()

redis_client = redis.from_url(settings.REDIS_PUBSUB_URL)

async def event_stream():
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("stratos_events")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield {
                    "data": message["data"].decode()
                }
    finally:
        await pubsub.unsubscribe("stratos_events")
        await pubsub.close()

@router.get("/events")
async def subscribe():
    return EventSourceResponse(event_stream())
