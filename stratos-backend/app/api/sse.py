import json

import redis.asyncio as redis
from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.db import models
from app.db.session import SessionLocal
from app.utils.auth_dep import user_id_from_token

router = APIRouter()

redis_client = redis.from_url(settings.REDIS_PUBSUB_URL)


def _session_owned_by(session_id: str, user_id: str) -> bool:
    db = SessionLocal()
    try:
        return (
            db.query(models.Session)
            .filter_by(id=session_id, user_id=user_id)
            .first()
            is not None
        )
    finally:
        db.close()


async def event_stream(session_id: str):
    """Forward only events belonging to ``session_id`` (server-side filter)."""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("stratos_events")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            raw = message["data"].decode()
            try:
                event = json.loads(raw)
            except (ValueError, TypeError):
                continue

            payload = event.get("payload") or {}
            if payload.get("session_id") != session_id:
                continue

            yield {"data": raw}
    finally:
        await pubsub.unsubscribe("stratos_events")
        await pubsub.close()


@router.get("/events/{session_id}")
async def subscribe(session_id: str, token: str = ""):
    # EventSource cannot set headers, so the JWT arrives as ?token=.
    user_id = user_id_from_token(token)
    if not user_id:
        raise HTTPException(401, "Invalid or expired token")

    if not _session_owned_by(session_id, user_id):
        # 404 (not 403) so we never leak which sessions exist.
        raise HTTPException(404, "Session not found")

    return EventSourceResponse(event_stream(session_id))
