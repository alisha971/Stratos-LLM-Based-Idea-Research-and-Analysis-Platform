import logging

from google.auth.exceptions import GoogleAuthError
from google.oauth2 import id_token
from google.auth.transport import requests
from app.config import settings

logger = logging.getLogger(__name__)


def verify_google_token(google_token: str):
    # Defense in depth: config.validate() already refuses to boot without this,
    # but never silently skip the audience check if it somehow got here unset.
    if not settings.GOOGLE_CLIENT_ID:
        return None

    try:
        user_info = id_token.verify_oauth2_token(
            google_token,
            requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except (GoogleAuthError, ValueError):
        return None
    except Exception:
        logger.exception("Unexpected error verifying Google token")
        return None

    if not user_info.get("email_verified"):
        return None

    return user_info
