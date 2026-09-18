import time

from app.core.config import Settings
from app.main import create_app
from app.models.identity import AuthSession, User
from fastapi.testclient import TestClient
from sqlalchemy import select


def account(client, username):
    credentials = {"username": username, "password": "a-strong-test-password"}
    registered = client.post("/api/v1/auth/register", json=credentials)
    assert registered.status_code == 201
    logged = client.post("/api/v1/auth/login", json=credentials)
    assert logged.status_code == 200
    return registered.json(), logged.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_two_users_isolated_and_cannot_inject_identity(client):
    alice, ta = account(client, "Alice")
    bob, tb = account(client, "Bob")
    assert alice["id"] != bob["id"]
    body = {"equipment": ["rice cooker"], "default_servings": 2}
    assert client.put("/api/v1/me/preferences", json=body, headers=auth(ta)).status_code == 200
    assert client.get("/api/v1/me/preferences", headers=auth(tb)).json()["equipment"] == []
    body["user_id"] = bob["id"]
    assert client.put("/api/v1/me/preferences", json=body, headers=auth(ta)).status_code == 422
    assert client.get("/api/v1/me", headers=auth(tb)).json()["id"] == bob["id"]


def test_password_and_session_storage_and_logout(client):
    user, token = account(client, "private_user")
    assert "password_hash" not in user
    with client.app.state.sessions() as db:
        stored = db.get(User, user["id"])
        assert stored.password_hash.startswith("$argon2")
        session = db.scalar(select(AuthSession))
        assert session.token_hash != token
        assert len(session.token_hash) == 64
    assert client.post("/api/v1/auth/logout", headers=auth(token)).status_code == 204
    assert client.get("/api/v1/me", headers=auth(token)).status_code == 401


def test_expired_missing_and_invalid_sessions(client):
    _, token = account(client, "expired_user")
    with client.app.state.sessions() as db:
        session = db.scalar(select(AuthSession))
        session.expires_at = int(time.time()) - 1
        db.commit()
    for headers in ({}, auth("incorrect"), auth(token)):
        response = client.get("/api/v1/me", headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


def test_duplicate_and_bad_credentials(client):
    account(client, "duplicate")
    body = {"username": "DUPLICATE", "password": "a-strong-test-password"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 409
    body["password"] = "wrong-test-password"
    assert client.post("/api/v1/auth/login", json=body).status_code == 401
    body["username"] = "not_registered"
    assert client.post("/api/v1/auth/login", json=body).status_code == 401


def test_validation_never_reflects_password(client):
    secret = "short!"
    response = client.post("/api/v1/auth/register", json={"username": "valid", "password": secret})
    assert response.status_code == 422
    assert secret not in response.text


def test_health(client):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200


def test_readiness_requires_migrations(tmp_path):
    url = f"sqlite:///{(tmp_path / 'empty.db').as_posix()}"
    with TestClient(create_app(Settings(database_url=url, _env_file=None))) as client:
        assert client.get("/health/live").status_code == 200
        result = client.get("/health/ready")
        assert result.status_code == 503
        assert "empty.db" not in result.text
