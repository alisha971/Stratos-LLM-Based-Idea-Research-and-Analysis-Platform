"""Rate limiting + global daily circuit breaker (security §4).

- Per-user limits via slowapi, keyed by the JWT ``sub`` when present.
- A global daily session cap backed by a single Redis counter (protects the
  wallet even if per-user limits are individually within bounds).
"""

from datetime import datetime, timezone

import redis
from fastapi import HTTPException, Request
from slowapi import Limiter

from app.config import settings
from app.utils.auth_dep import user_id_from_token

_redis = redis.Redis.from_url(settings.REDIS_PUBSUB_URL)


def user_key(request: Request) -> str:
    """slowapi key function: prefer authenticated user id, else client IP."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        uid = user_id_from_token(auth.removeprefix("Bearer ").strip())
        if uid:
            return f"user:{uid}"
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


limiter = Limiter(key_func=user_key)


def enforce_global_daily_cap() -> None:
    """Increment today's session counter; raise 503 past the configured cap."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    counter_key = f"stratos:daily_sessions:{today}"
    try:
        count = _redis.incr(counter_key)
        if count == 1:
            # First hit today: expire the counter after 48h so it self-cleans.
            _redis.expire(counter_key, 60 * 60 * 48)
    except redis.RedisError:
        # Fail-open on Redis outage rather than blocking all traffic.
        return

    if count > settings.GLOBAL_DAILY_SESSION_CAP:
        raise HTTPException(
            status_code=503,
            detail="Daily capacity reached. Please try again tomorrow.",
        )
