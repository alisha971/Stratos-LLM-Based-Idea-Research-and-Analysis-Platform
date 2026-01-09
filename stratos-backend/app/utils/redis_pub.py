# app/utils/redis_pub.py

import json
import redis
from app.config import settings

redis_client = redis.Redis.from_url(settings.REDIS_PUBSUB_URL)

def publish_event(event_type: str, payload: dict):
    """
    Publish JSON-encoded events to Redis Pub/Sub.
    """
    message = {
        "type": event_type,
        "payload": payload,
    }

    # ✅ MUST be JSON
    redis_client.publish(
        "stratos_events",
        json.dumps(message),
    )
