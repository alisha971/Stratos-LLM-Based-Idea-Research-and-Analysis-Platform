# app/utils/redis_pub.py

import json
import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

redis_client = redis.Redis.from_url(settings.REDIS_PUBSUB_URL)

# report_id -> session_id is immutable, so an in-process cache is safe and
# spares us a DB round-trip on every high-volume event (e.g. section_chunk).
_session_id_cache: dict[str, str] = {}


def _resolve_session_id(report_id: str) -> str | None:
    if report_id in _session_id_cache:
        return _session_id_cache[report_id]

    # Lazy import to avoid import cycles at module load.
    from app.db import models
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        report = db.query(models.Report).filter_by(id=report_id).first()
        if report and report.session_id:
            _session_id_cache[report_id] = report.session_id
            return report.session_id
    except Exception:
        logger.exception("[SSE] Failed to resolve session_id for report_id=%s", report_id)
    finally:
        db.close()
    return None


def publish_event(event_type: str, payload: dict):
    """Publish a JSON event to Redis Pub/Sub.

    Contract guarantee (B1.4 / doc 05 §4): every payload carries ``session_id``.
    Call sites that only know ``report_id`` are enriched automatically here.
    """
    if "session_id" not in payload and payload.get("report_id"):
        session_id = _resolve_session_id(payload["report_id"])
        if session_id:
            payload = {**payload, "session_id": session_id}

    message = {
        "type": event_type,
        "payload": payload,
    }

    redis_client.publish(
        "stratos_events",
        json.dumps(message),
    )
