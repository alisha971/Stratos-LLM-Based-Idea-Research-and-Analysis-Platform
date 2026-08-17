"""Auth dependency: resolves the caller's user id from a Bearer JWT.

Security notes:
- Algorithm is pinned in ``verify_jwt`` (``algorithms=["HS256"]``); the token's
  own header is never trusted (blocks ``alg=none``).
- The ``dev`` escape-hatch token works ONLY when ENV=development AND
  DEV_AUTH_BYPASS=true (enforced at boot by ``settings.validate``).
"""

from fastapi import Header, HTTPException

from app.config import settings
from app.utils.jwt_utils import verify_jwt

DEV_USER_ID = "dev-user"


def _resolve_user_id(token: str) -> str:
    if (
        settings.ENV == "development"
        and settings.DEV_AUTH_BYPASS
        and token == "dev"
    ):
        return DEV_USER_ID

    payload = verify_jwt(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload["sub"]


def current_user_id(authorization: str = Header(default="")) -> str:
    """FastAPI dependency. Returns the authenticated user id or raises 401."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    return _resolve_user_id(token)


def user_id_from_token(token: str | None) -> str | None:
    """Non-raising variant for the SSE query-param path. Returns None if invalid."""
    if not token:
        return None
    try:
        return _resolve_user_id(token)
    except HTTPException:
        return None
