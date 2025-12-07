from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
import redis
import json
from app.config import settings

router = APIRouter()

redis_client = redis.Redis.from_url(settings.REDIS_PUBSUB_URL)

async def event_stream():
    pubsub = redis_client.pubsub()
    pubsub.subscribe("stratos_events")

    for message in pubsub.listen():
        if message["type"] == "message":
            raw = message["data"].decode()
            yield {"data": raw}

@router.get("/events")
async def subscribe_to_events():
    return EventSourceResponse(event_stream())
