"""Auth release-blocker tests (security §1 + ship-timeline Day-5 exit criteria).

Covers: Google login happy path, invalid Google token, missing/invalid bearer
token on a protected route, cross-user access returning 404 (never 403), and
the dev-bypass path producing a usable, FK-valid user.

Requires a running local Postgres per SETUP.md (same DB the app itself uses
via DATABASE_URL) -- there's no separate test DB/sqlite swap here because the
schema uses Postgres-only column types (JSONB). Rows created by these tests
are cleaned up in a fixture teardown.
"""

from pathlib import Path
import sys
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import models
from app.db.database import SessionLocal
from app.main import app
from app.utils.auth_dep import DEV_USER_ID
from app.utils.jwt_utils import create_jwt

client = TestClient(app)

_created_user_ids: list[str] = []


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        if _created_user_ids:
            session_ids = [
                row.id
                for row in db.query(models.Session.id).filter(
                    models.Session.user_id.in_(_created_user_ids)
                )
            ]
            if session_ids:
                db.query(models.ChatMessage).filter(
                    models.ChatMessage.session_id.in_(session_ids)
                ).delete(synchronize_session=False)
                db.query(models.Report).filter(
                    models.Report.session_id.in_(session_ids)
                ).delete(synchronize_session=False)
                db.query(models.Session).filter(
                    models.Session.id.in_(session_ids)
                ).delete(synchronize_session=False)
            db.query(models.User).filter(
                models.User.id.in_(_created_user_ids)
            ).delete(synchronize_session=False)
            db.commit()
        _created_user_ids.clear()
    finally:
        db.close()


def _make_user_and_token():
    db = SessionLocal()
    try:
        email = f"test-{uuid.uuid4()}@example.com"
        user = models.User(email=email, google_sub=f"sub-{email}", name="Test User")
        db.add(user)
        db.commit()
        db.refresh(user)
        _created_user_ids.append(user.id)
        token = create_jwt({"sub": user.id, "email": user.email})
        return user, token
    finally:
        db.close()


def test_google_login_happy_path():
    email = f"new-{uuid.uuid4()}@example.com"
    fake_user_info = {
        "sub": f"google-sub-{uuid.uuid4()}",
        "email": email,
        "email_verified": True,
        "name": "New User",
        "picture": "https://example.com/pic.png",
    }
    with patch("app.api.auth.verify_google_token", return_value=fake_user_info):
        resp = client.post("/auth/google", json={"id_token": "fake-id-token"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == email
    _created_user_ids.append(body["user"]["id"])


def test_google_login_invalid_token_rejected():
    with patch("app.api.auth.verify_google_token", return_value=None):
        resp = client.post("/auth/google", json={"id_token": "garbage"})
    assert resp.status_code == 401


def test_protected_route_requires_token():
    resp = client.post(
        "/orchestrate/start-session", json={"idea_description": "a new idea"}
    )
    assert resp.status_code == 401


def test_protected_route_rejects_garbage_bearer_token():
    resp = client.post(
        "/orchestrate/start-session",
        json={"idea_description": "a new idea"},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert resp.status_code == 401


def test_cross_user_session_access_is_404_not_403():
    owner, owner_token = _make_user_and_token()
    _, other_token = _make_user_and_token()

    db = SessionLocal()
    try:
        session = models.Session(user_id=owner.id, idea_description="idea for test")
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id
    finally:
        db.close()

    resp = client.get(
        f"/orchestrate/status/{session_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404

    resp_owner = client.get(
        f"/orchestrate/status/{session_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    # Sanity check: the 404 above is an ownership check, not a routing bug.
    assert resp_owner.status_code == 200


def test_dev_bypass_creates_usable_fk_valid_user(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ENV", "development")
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)

    resp = client.post(
        "/orchestrate/start-session",
        json={"idea_description": "a dev-mode idea for testing"},
        headers={"Authorization": "Bearer dev"},
    )
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        dev_user = db.query(models.User).filter_by(id=DEV_USER_ID).first()
        assert dev_user is not None
        created_session_id = resp.json().get("session_id")
    finally:
        db.close()

    if created_session_id:
        db = SessionLocal()
        try:
            # dev-user is a persistent seeded row (reused across dev-bypass
            # calls), so only clean up what this test created under it.
            db.query(models.ChatMessage).filter_by(
                session_id=created_session_id
            ).delete()
            db.query(models.Report).filter_by(
                session_id=created_session_id
            ).delete()
            db.query(models.Session).filter_by(id=created_session_id).delete()
            db.commit()
        finally:
            db.close()
