"""Auth dependency: resolves the caller's user id from a Bearer JWT.

Security notes:
- Algorithm is pinned in ``verify_jwt`` (``algorithms=["HS256"]``); the token's
  own header is never trusted (blocks ``alg=none``).
- The ``dev`` escape-hatch token works ONLY when ENV=development AND
  DEV_AUTH_BYPASS=true (enforced at boot by ``settings.validate``).
"""

from fastapi import Header, HTTPException, Query

from app.config import settings
from app.utils.jwt_utils import verify_jwt

DEV_USER_ID = "dev-user"
DEV_USER_EMAIL = "dev@stratos.local"


def _ensure_dev_user_exists() -> None:
    """Upsert the dev-bypass user row so it satisfies the users FK.

    Imported lazily to avoid a hard dependency on the DB layer for callers
    that never hit the dev-bypass path.
    """
    from app.db import models
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        if db.query(models.User).filter_by(id=DEV_USER_ID).first():
            return
        db.add(models.User(id=DEV_USER_ID, email=DEV_USER_EMAIL, name="Dev User"))
        db.commit()
    finally:
        db.close()


def _resolve_user_id(token: str) -> str:
    if (
        settings.ENV == "development"
        and settings.DEV_AUTH_BYPASS
        and token == "dev"
    ):
        _ensure_dev_user_exists()
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


def current_user_id_or_query_token(
    authorization: str = Header(default=""),
    token: str = Query(default=""),
) -> str:
    """Like ``current_user_id``, but also accepts ``?token=`` as a fallback.

    For endpoints reached via plain browser navigation (e.g. PDF download)
    where JS can't attach an Authorization header — same pattern as the SSE
    stream's ``?token=``.
    """
    if authorization.startswith("Bearer "):
        return _resolve_user_id(authorization.removeprefix("Bearer ").strip())
    if token:
        return _resolve_user_id(token)
    raise HTTPException(status_code=401, detail="Missing bearer token")


def user_id_from_token(token: str | None) -> str | None:
    """Non-raising variant for the SSE query-param path. Returns None if invalid."""
    if not token:
        return None
    try:
        return _resolve_user_id(token)
    except HTTPException:
        return None
