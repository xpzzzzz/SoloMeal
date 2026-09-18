from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier

import pytest
from test_food import stock
from test_identity import account, auth
from test_planning import plan, setup
from test_plans import confirm, create


def cancel(client, h, p, version=1, key="cancel-plan-01"):
    return client.post(f"/api/v1/plans/{p['id']}/cancel", json={"expected_version": version},
                       headers={**h, "Idempotency-Key": key})


def test_cancel_history_owner_replay_and_terminal(client):
    h, item, rid = setup(client)
    stock(client, h, item)
    p = create(client, h, rid)
    path = f"/api/v1/plans/{p['id']}/revisions"
    before = client.get(path, headers=h).json()
    assert [v["version"] for v in before] == [1]
    response = client.post(path, headers={**h, "Idempotency-Key": "revision-second"}, json={
        "recipe_id": rid, "expected_version": 1, "constraints": {"servings": 2},
    })
    assert response.status_code == 200
    versions = client.get(path, headers=h).json()
    assert versions[0] == before[0] and versions[1]["version"] == 2
    assert versions[1]["snapshot"]["candidate"]["servings"] == 2
    _, token = account(client, "other")
    assert client.get(path, headers=auth(token)).status_code == 404
    assert cancel(client, auth(token), p, 2).status_code == 404
    assert cancel(client, h, p).status_code == 409
    result = cancel(client, h, p, 2)
    assert result.status_code == 200 and result.json()["status"] == "cancelled"
    assert cancel(client, h, p, 2).json() == result.json()
    assert cancel(client, h, p, 2, "cancel-another-key").status_code == 409
    assert confirm(client, h, p, version=2).status_code == 409
    assert client.post(path, headers={**h, "Idempotency-Key": "edit-cancelled-plan"}, json={
        "recipe_id": rid, "expected_version": 2,
    }).status_code == 409
    assert client.get(path, headers=h).json() == versions
    assert client.get("/api/v1/cooking", headers=h).json() == []


def test_scoring_weights_and_snapshot(client):
    h, item, rid = setup(client)
    stock(client, h, item, "40", expires=date.today().isoformat())
    weights = {"inventory": 20, "expiry": 30, "repetition": 5, "purchase_cost": 2}
    quote = {"ingredient_id": item, "package_quantity": "50", "package_price": "3",
             "source": "test", "observed_on": date.today().isoformat()}
    body = {"score_weights": weights, "quotes": [quote]}
    result = plan(client, h, body)
    candidate = result["candidates"][0]
    assert candidate["score"] == 19  # .5*20 + .5*30 - 3*2
    assert candidate["score_weights"] == weights
    assert result == plan(client, h, body)
    assert plan(client, h, {**body, "equipment": []})["candidates"] == []
    for invalid in ({"inventory": -1}, {"inventory": True}, {"expiry": 0.5},
                    {"other": 10}, {"inventory": 0, "expiry": 0, "repetition": 0, "purchase_cost": 0}):
        assert client.post("/api/v1/recommendations", headers=h, json={"score_weights": invalid}).status_code == 422
    saved = client.post("/api/v1/plans", headers={**h, "Idempotency-Key": "weighted-plan-01"},
                        json={"recipe_id": rid, "constraints": body})
    assert saved.status_code == 201
    assert saved.json()["snapshot"]["request"]["score_weights"] == weights


def test_confirmation_after_date_rollover(client, monkeypatch):
    from app.services import plans

    h, item, rid = setup(client)
    stock(client, h, item)
    p = create(client, h, rid)
    tomorrow = date.today() + timedelta(days=1)

    class NextDate(date):
        @classmethod
        def today(cls):
            return tomorrow

    monkeypatch.setattr(plans, "date", NextDate)
    result = confirm(client, h, p)
    assert result.status_code == 409 and result.json()["error"]["code"] == "PLAN_STALE"
    assert client.get("/api/v1/cooking", headers=h).json() == []


def test_mysql_cancel_confirm_race(client):
    if client.app.state.engine.dialect.name != "mysql":
        pytest.skip("MySQL row-lock integration")
    h, item, rid = setup(client)
    stock(client, h, item)
    p = create(client, h, rid)
    gate = Barrier(2)

    def run(n):
        gate.wait(timeout=10)
        return cancel(client, h, p) if n == 0 else confirm(client, h, p)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, (0, 1)))
    assert sorted(r.status_code for r in results) == [200, 409]
    state = client.get(f"/api/v1/plans/{p['id']}", headers=h).json()["status"]
    assert len(client.get("/api/v1/cooking", headers=h).json()) == (1 if state == "completed" else 0)
