from decimal import Decimal

from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from test_agent import Scripted, action, call, create, step
from test_food import stock
from test_planning import setup


def prepare(client, h, name, body):
    client.app.state.agent_model = Scripted(call(name, body))
    rid = create(client, h)
    result = step(client, h, rid)
    assert result["status"] == "awaiting_confirmation", result
    return rid, result


def test_inventory_approval_is_single_transaction(client):
    h, item, _ = setup(client)
    rid, proposal = prepare(client, h, "prepare_inventory", {
        "ingredient_id": item, "quantity": "0.1", "unit": "kg",
    })
    assert proposal["pending"]["preview"]["quantity"] == "100.0"
    assert client.get("/api/v1/inventory", headers=h).json() == []
    result = action(client, h, rid, "approve")
    assert result.status_code == 200, result.text
    assert result.json()["result"]["action"] == "prepare_inventory"
    assert action(client, h, rid, "approve").json() == result.json()
    rows = client.get("/api/v1/inventory", headers=h).json()
    assert len(rows) == 1 and Decimal(rows[0]["quantity"]) == 100
    assert len(client.get("/api/v1/inventory/events", headers=h).json()) == 1


def test_cooking_confirmation_stales_on_adjustment(client):
    h, item, recipe = setup(client)
    batch = stock(client, h, item)
    rid, _ = prepare(client, h, "prepare_cooking", {"recipe_id": recipe, "servings": 1})
    assert client.get("/api/v1/cooking", headers=h).json() == []
    assert client.patch(f"/api/v1/inventory/{batch['id']}", headers={
        **h, "Idempotency-Key": "adjust-after-prepare",
    }, json={"quantity": "99", "expected_version": 1}).status_code == 200
    result = action(client, h, rid, "approve")
    assert result.status_code == 409 and result.json()["error"]["code"] == "PLAN_STALE"
    assert client.get("/api/v1/cooking", headers=h).json() == []


def test_cooking_approval_and_undo_preview(client):
    h, item, recipe = setup(client)
    stock(client, h, item)
    rid, _ = prepare(client, h, "prepare_cooking", {"recipe_id": recipe, "servings": 1})
    result = action(client, h, rid, "approve")
    assert result.status_code == 200, result.text
    record = result.json()["result"]["operation_result"]
    assert Decimal(client.get("/api/v1/inventory", headers=h).json()[0]["quantity"]) == 20
    client.app.state.agent_model = Scripted(call("prepare_undo", {"cooking_id": record["id"]}))
    next_run = client.post("/api/v1/agent/runs", headers={**h, "Idempotency-Key": "undo-run-01"},
                           json={"message": "刚才记错了", "parent_run_id": rid}).json()
    preview = step(client, h, next_run["id"])
    assert preview["pending"]["preview"]["ingredients"][0]["quantity"] == "80.000"
    assert Decimal(client.get("/api/v1/inventory", headers=h).json()[0]["quantity"]) == 20
    headers = {**h, "Idempotency-Key": "approve-undo-01"}
    url = f"/api/v1/agent/runs/{next_run['id']}/approve"
    for _ in range(2):
        assert client.post(url, headers=headers).status_code == 200
    assert Decimal(client.get("/api/v1/inventory", headers=h).json()[0]["quantity"]) == 100


def test_expired_or_cancelled_preparation_cannot_write(client, monkeypatch):
    from app.services import agent_actions

    h, item, _ = setup(client)
    rid, proposal = prepare(client, h, "prepare_inventory", {
        "ingredient_id": item, "quantity": "100", "unit": "g",
    })
    monkeypatch.setattr(agent_actions.time, "time", lambda: proposal["pending"]["expires_at"] + 1)
    result = action(client, h, rid, "approve")
    assert result.status_code == 409 and result.json()["error"]["code"] == "CONFIRMATION_EXPIRED"
    assert action(client, h, rid, "cancel").status_code == 200
    assert action(client, h, rid, "approve").status_code == 409
    assert client.get("/api/v1/inventory", headers=h).json() == []


def test_approval_failure_rolls_back_business_and_run(client):
    h, item, _ = setup(client)
    rid, _ = prepare(client, h, "prepare_inventory", {
        "ingredient_id": item, "quantity": "100", "unit": "g",
    })

    def fail(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("INSERT INTO INVENTORY_EVENTS"):
            raise IntegrityError(statement, {}, RuntimeError("injected"))

    engine = client.app.state.engine
    event.listen(engine, "before_cursor_execute", fail)
    try:
        assert action(client, h, rid, "approve").status_code == 409
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert client.get("/api/v1/inventory", headers=h).json() == []
    assert client.get(f"/api/v1/agent/runs/{rid}", headers=h).json()["status"] == "awaiting_confirmation"
    assert action(client, h, rid, "approve").status_code == 200


def test_prepare_cooking_cannot_bypass_preferences(client):
    h, item, recipe = setup(client)
    stock(client, h, item)
    assert client.put("/api/v1/me/preferences", headers=h, json={
        "equipment": ["rice cooker"], "excluded_ingredients": ["rice"],
    }).status_code == 200
    client.app.state.agent_model = Scripted(call("prepare_cooking", {"recipe_id": recipe, "servings": 1}))
    result = step(client, h, create(client, h))
    assert result["status"] == "ready" and not result["pending"]
    assert result["events"][0]["result"]["error"]["code"] == "PLAN_INFEASIBLE"
