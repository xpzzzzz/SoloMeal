from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from test_food import stock
from test_identity import account, auth
from test_planning import setup


def create(client, h, rid):
    response = client.post(
        "/api/v1/plans", headers={**h, "Idempotency-Key": "plan-create-01"}, json={"recipe_id": rid}
    )
    assert response.status_code == 201, response.text
    return response.json()


def confirm(client, h, p, key="plan-confirm-01", version=1):
    return client.post(
        "/api/v1/plans/" + p["id"] + "/confirm",
        headers={**h, "Idempotency-Key": key},
        json={"expected_version": version},
    )


def test_confirm_replay_and_owner(client):
    h, item, rid = setup(client)
    stock(client, h, item)
    p = create(client, h, rid)
    assert p["status"] == "pending"
    assert create(client, h, rid)["id"] == p["id"]
    _, token = account(client, "other")
    assert confirm(client, auth(token), p).status_code == 404
    a = confirm(client, h, p)
    assert a.status_code == 200, a.text
    assert confirm(client, h, p).json() == a.json()
    assert confirm(client, h, p, key="different-confirm").status_code == 409
    assert client.get("/api/v1/plans/" + p["id"], headers=h).json()["status"] == "completed"
    assert len(client.get("/api/v1/cooking", headers=h).json()) == 1


def test_stale_stock_revision_and_old_version(client):
    h, item, rid = setup(client)
    stock(client, h, item)
    p = create(client, h, rid)
    stock(client, h, item, key="additional-stock")
    a = confirm(client, h, p)
    assert a.status_code == 409 and a.json()["error"]["code"] == "PLAN_STALE"
    assert client.get("/api/v1/cooking", headers=h).json() == []
    response = client.post(
        "/api/v1/plans/" + p["id"] + "/revisions",
        headers={**h, "Idempotency-Key": "revise-plan-01"},
        json={"recipe_id": rid, "expected_version": 1},
    )
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2
    assert confirm(client, h, p).status_code == 409
    assert confirm(client, h, p, key="confirm-version-2", version=2).status_code == 200


def test_preference_change_and_insufficient_rollback(client):
    h, item, rid = setup(client)
    p = create(client, h, rid)
    assert confirm(client, h, p).json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert client.get("/api/v1/plans/" + p["id"], headers=h).json()["status"] == "pending"
    assert (
        client.put(
            "/api/v1/me/preferences",
            headers=h,
            json={"equipment": ["rice cooker"], "excluded_ingredients": ["rice"]},
        ).status_code
        == 200
    )
    assert confirm(client, h, p).json()["error"]["code"] == "PLAN_STALE"
    assert client.get("/api/v1/cooking", headers=h).json() == []


def test_concurrent_confirmation(client):
    if client.app.state.engine.dialect.name != "mysql":
        pytest.skip("MySQL row-lock integration")
    h, item, rid = setup(client)
    stock(client, h, item, qty="200")
    p = create(client, h, rid)
    barrier = Barrier(2)

    def run(key):
        barrier.wait()
        return confirm(client, h, p, key=key).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["concurrent-confirm-a", "concurrent-confirm-b"]))
    assert sorted(results) == [200, 409]
    assert len(client.get("/api/v1/cooking", headers=h).json()) == 1


def test_new_alias_cannot_bypass_saved_exclusion(client):
    h, item, rid = setup(client)
    stock(client, h, item)
    assert (
        client.put(
            "/api/v1/me/preferences",
            headers=h,
            json={"equipment": ["rice cooker"], "excluded_ingredients": ["米饭"]},
        ).status_code
        == 200
    )
    p = create(client, h, rid)
    assert (
        client.post(
            f"/api/v1/ingredients/{item}/aliases", headers=h, json={"alias": "米饭"}
        ).status_code
        == 201
    )
    assert confirm(client, h, p).json()["error"]["code"] == "PLAN_STALE"
    assert client.get("/api/v1/cooking", headers=h).json() == []


def test_unknown_budget_cannot_confirm(client):
    h, item, rid = setup(client)
    response = client.post(
        "/api/v1/plans",
        headers={**h, "Idempotency-Key": "unknown-budget-plan"},
        json={"recipe_id": rid, "constraints": {"budget": "10"}},
    )
    assert response.status_code == 201, response.text
    assert confirm(client, h, response.json()).json()["error"]["code"] == "BUDGET_UNKNOWN"
    assert client.get("/api/v1/cooking", headers=h).json() == []
