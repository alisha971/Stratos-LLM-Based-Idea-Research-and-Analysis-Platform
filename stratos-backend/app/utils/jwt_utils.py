import logging

from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from app.config import settings

logger = logging.getLogger(__name__)


def create_jwt(payload: dict):
    now = datetime.now(timezone.utc)
    claims = {**payload, "iat": now, "exp": now + timedelta(days=7)}
    return jwt.encode(claims, settings.JWT_SECRET, settings.JWT_ALGO)


def verify_jwt(token: str):
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGO])
    except JWTError:
        return None
    except Exception:
        logger.exception("Unexpected error verifying JWT")
        return None
