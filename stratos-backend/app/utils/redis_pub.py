import redis
from app.config import settings

redis_client = redis.Redis.from_url(settings.REDIS_PUBSUB_URL)

def publish_event(event_type: str, payload: dict):
    message = {
        "type": event_type,
        "payload": payload
    }
    redis_client.publish("stratos_events", str(message))
