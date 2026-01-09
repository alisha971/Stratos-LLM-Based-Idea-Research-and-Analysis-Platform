import json
import redis
from app.config import settings
from app.db.session import SessionLocal
from app.services.orchestrator_service import OrchestratorService

def start_event_listener():
    """
    Background Redis Pub/Sub listener.
    Listens for clarification_ready and triggers orchestrator transitions.
    """
    r = redis.Redis.from_url(settings.REDIS_PUBSUB_URL)
    pubsub = r.pubsub()
    pubsub.subscribe("stratos_events")

    for message in pubsub.listen():
        if message["type"] != "message":
            continue

        try:
            event = json.loads(message["data"])
        except Exception:
            continue

        event_type = event.get("type")
        payload = event.get("payload", {})

        if event_type == "clarification_ready":
            db = SessionLocal()
            try:
                OrchestratorService.handle_clarification_ready(
                    db=db,
                    session_id=payload["session_id"],
                    payload=payload,
                )
            finally:
                db.close()
