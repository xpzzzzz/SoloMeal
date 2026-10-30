from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.main import create_app
from app.models.food import Ingredient, InventoryBatch
from app.services.proactivity_store import tick_user
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_food import create_ingredient, recipe, stock
from test_identity import account, auth

NOW = datetime(2026, 10, 30, 4, tzinfo=timezone.utc)


def seeded(client, username="proactive"):
    user, token = account(client, username)
    headers = auth(token)
    ingredient = create_ingredient(client, headers, "spinach")
    recipe_id = recipe(client, headers, ingredient)
    batch = stock(client, headers, ingredient, "300", expires=(NOW.date() + timedelta(days=1)).isoformat())
    client.app.state.proactivity_clock = lambda: NOW
    with client.app.state.sessions() as db:
        assert tick_user(db, user["id"], NOW)["created"] == 1
    item = client.get("/api/v1/proactivity/inbox", headers=headers).json()["items"][0]
    return user, headers, item, batch, recipe_id


def test_inbox_requires_auth(client):
    assert client.get("/api/v1/proactivity/inbox").status_code == 401


def test_inbox_returns_only_own_items(client):
    _, headers, item, _, _ = seeded(client)
    _, token = account(client, "other")
    other = auth(token)
    assert client.get("/api/v1/proactivity/inbox", headers=other).json()["items"] == []
    response = client.post(f"/api/v1/proactivity/items/{item['id']}/dismiss", json={},
                           headers={**other, "Idempotency-Key": "other-key"})
    assert response.status_code == 404
    assert len(client.get("/api/v1/proactivity/inbox", headers=headers).json()["items"]) == 1


def test_accept_marks_accepted_and_returns_action(client):
    _, headers, item, _, recipe_id = seeded(client)
    response = client.post(f"/api/v1/proactivity/items/{item['id']}/accept", json={"expected_version": 0},
                           headers={**headers, "Idempotency-Key": "accept-key"})
    assert response.status_code == 200, response.text
    assert response.json()["item"]["status"] == "accepted"
    assert response.json()["action"]["recipe_id"] == recipe_id
    resumed = client.get("/api/v1/proactivity/inbox", headers=headers).json()["items"]
    assert len(resumed) == 1 and resumed[0]["status"] == "accepted"
    done = client.post(f"/api/v1/proactivity/items/{item['id']}/complete",
                       headers={**headers, "Idempotency-Key": "complete-key"})
    assert done.status_code == 200
    assert client.post(f"/api/v1/proactivity/items/{item['id']}/complete",
                       headers={**headers, "Idempotency-Key": "complete-key"}).json() == done.json()
    assert client.get("/api/v1/proactivity/inbox", headers=headers).json()["items"] == []


def test_accepted_item_can_be_abandoned_without_suppressing_kind(client):
    _, headers, item, _, _ = seeded(client)
    path = f"/api/v1/proactivity/items/{item['id']}"
    assert client.post(path + "/accept", json={"expected_version": 0},
                       headers={**headers, "Idempotency-Key": "accept-key"}).status_code == 200
    result = client.post(path + "/abandon", headers={**headers, "Idempotency-Key": "abandon-key"})
    assert result.status_code == 200 and result.json()["item"]["status"] == "abandoned"
    inbox = client.get("/api/v1/proactivity/inbox", headers=headers).json()
    assert inbox["items"] == [] and inbox["meta"]["suppressed_kinds"] == []


def test_action_completion_requires_owner_and_idempotency(client):
    _, headers, item, _, _ = seeded(client)
    _, other_token = account(client, "other_recovery")
    path = f"/api/v1/proactivity/items/{item['id']}"
    assert client.post(path + "/accept", json={"expected_version": 0},
                       headers={**headers, "Idempotency-Key": "accept-key"}).status_code == 200
    assert client.post(path + "/complete", headers=headers).status_code == 422
    for action in ("complete", "abandon"):
        response = client.post(path + "/" + action,
                               headers={**auth(other_token), "Idempotency-Key": "other-key"})
        assert response.status_code == 404
    assert client.get("/api/v1/proactivity/inbox", headers=auth(other_token)).json()["items"] == []
    assert len(client.get("/api/v1/proactivity/inbox", headers=headers).json()["items"]) == 1


def test_accept_with_stale_snapshot_returns_409(client):
    _, headers, item, batch, _ = seeded(client)
    with client.app.state.sessions() as db:
        row = db.get(InventoryBatch, batch["id"])
        row.version += 1
        db.commit()
    response = client.post(f"/api/v1/proactivity/items/{item['id']}/accept", json={"expected_version": 0},
                           headers={**headers, "Idempotency-Key": "accept-key"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "PROACTIVE_STALE"


def test_dismiss_requires_idempotency_key(client):
    _, headers, item, _, _ = seeded(client)
    assert client.post(f"/api/v1/proactivity/items/{item['id']}/dismiss", json={}, headers=headers).status_code == 422


def test_dismiss_is_idempotent_on_replay(client):
    _, headers, item, _, _ = seeded(client)
    path = f"/api/v1/proactivity/items/{item['id']}/dismiss"
    headers = {**headers, "Idempotency-Key": "dismiss-key"}
    first = client.post(path, json={"reason": "too_often"}, headers=headers)
    again = client.post(path, json={"reason": "too_often"}, headers=headers)
    assert first.status_code == again.status_code == 200 and first.json() == again.json()
    assert client.post(path, json={"reason": "already_done"}, headers=headers).status_code == 409


def test_settings_patch_version_conflict_returns_409(client):
    _, token = account(client, "settings")
    headers = auth(token)
    body = {"expected_version": 0, "enabled": True, "daily_limit": 2,
            "quiet_start": "22:00", "quiet_end": "08:00", "snooze_until": None}
    first = client.patch("/api/v1/proactivity/settings", json=body,
                         headers={**headers, "Idempotency-Key": "settings-1"})
    assert first.status_code == 200 and first.json()["version"] == 1
    conflict = client.patch("/api/v1/proactivity/settings", json=body,
                            headers={**headers, "Idempotency-Key": "settings-2"})
    assert conflict.status_code == 409


def test_tick_requires_internal_token(client):
    assert client.post("/internal/tick", json={}).status_code == 404
    client.app.state.settings.tick_token = SecretStr("test-internal-token")
    assert client.post("/internal/tick", json={}).status_code == 401
    assert client.post("/internal/tick", json={}, headers={"X-Internal-Token": "wrong"}).status_code == 401
    result = client.post("/internal/tick", json={}, headers={"X-Internal-Token": "test-internal-token"})
    assert result.status_code == 200 and result.json()["users"] == 0


def test_home_still_returns_four_sections(client):
    _, token = account(client, "home_check")
    body = client.get("/api/v1/home", headers=auth(token)).json()
    assert set(body["sections"]) == {"attention", "recommendations", "shopping", "recent"}


def test_simulate_is_disabled_by_default(client):
    assert client.post("/api/v1/proactivity/simulate", json={"days": 1}).status_code == 404


def test_simulate_is_user_scoped_and_idempotent(client):
    alice, token = account(client, "alice_demo")
    _, other_token = account(client, "bob_demo")
    with client.app.state.sessions() as db:
        item = Ingredient(user_id=alice["id"], name="菠菜", unit="g")
        db.add(item)
        db.flush()
        db.add(InventoryBatch(user_id=alice["id"], ingredient_id=item.id, quantity=100,
                              expires_on=NOW.date() + timedelta(days=2)))
        db.commit()
    app = create_app(Settings(_env_file=None, database_url=client.app.state.settings.database_url, demo_mode=True))
    app.state.proactivity_clock = lambda: NOW
    with TestClient(app) as demo:
        headers = {**auth(token), "Idempotency-Key": "simulate-1"}
        first = demo.post("/api/v1/proactivity/simulate", json={"days": 1}, headers=headers)
        again = demo.post("/api/v1/proactivity/simulate", json={"days": 1}, headers=headers)
        assert first.status_code == again.status_code == 200
        assert first.json() == again.json() and first.json()["created"] == 1
        assert first.json()["display_date"] == again.json()["display_date"] == "2026-10-31"
        assert app.state.proactivity_offsets == {alice["id"]: 1}
        assert demo.get("/api/v1/proactivity/inbox", headers=auth(other_token)).json()["meta"]["display_date"] == "2026-10-30"
        assert demo.post("/api/v1/proactivity/simulate", json={"days": 1}, headers=auth(token)).status_code == 422
