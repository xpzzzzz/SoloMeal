from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from app.models.food import InventoryBatch, Operation
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from test_identity import account, auth


def create_ingredient(client, headers, name="rice", unit="g"):
    result = client.post("/api/v1/ingredients", json={"name": name, "unit": unit}, headers=headers)
    assert result.status_code == 201, result.text
    return result.json()["id"]


def stock(client, headers, item, qty="100", key="stock-001", expires=None):
    body = {"ingredient_id": item, "quantity": qty, "unit": "g"}
    if expires is not None:
        body.update(expires_on=expires, expiry_source="user")
    result = client.post(
        "/api/v1/inventory", json=body, headers={**headers, "Idempotency-Key": key}
    )
    assert result.status_code == 201, result.text
    return result.json()


def recipe(client, headers, item, qty="80"):
    body = {
        "name": "rice bowl",
        "servings": 1,
        "minutes": 20,
        "equipment": ["rice cooker"],
        "steps": ["Cook rice"],
        "source": "test fixture",
        "ingredients": [{"ingredient_id": item, "quantity": qty, "unit": "g"}],
    }
    response = client.post("/api/v1/recipes", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def cook(client, headers, recipe_id, key="cooking-001"):
    return client.post(
        "/api/v1/cooking",
        json={"recipe_id": recipe_id, "servings": 1},
        headers={**headers, "Idempotency-Key": key},
    )


def quantities(client, headers):
    return {
        b["id"]: Decimal(b["quantity"])
        for b in client.get("/api/v1/inventory", headers=headers).json()
    }


def test_batch_conversion_aliases_and_isolation(client):
    _, ta = account(client, "alice")
    _, tb = account(client, "bob")
    ha, hb = auth(ta), auth(tb)
    item = create_ingredient(client, ha, "tomato")
    assert (
        client.post(
            f"/api/v1/ingredients/{item}/aliases", json={"alias": "西红柿"}, headers=ha
        ).status_code
        == 201
    )
    assert (
        client.get("/api/v1/ingredients/resolve", params={"name": "西红柿"}, headers=ha).json()[
            "id"
        ]
        == item
    )
    assert (
        client.get("/api/v1/ingredients/resolve", params={"name": "西红柿"}, headers=hb).status_code
        == 404
    )
    body = {"ingredient_id": item, "quantity": "0.5", "unit": "kg"}
    response = client.post(
        "/api/v1/inventory", json=body, headers={**ha, "Idempotency-Key": "convert-001"}
    )
    assert response.status_code == 201
    assert Decimal(response.json()["quantity"]) == 500
    assert client.get("/api/v1/inventory", headers=hb).json() == []
    assert (
        client.post(
            "/api/v1/inventory", json=body, headers={**hb, "Idempotency-Key": "attack-001"}
        ).status_code
        == 404
    )
    body["unit"] = "ml"
    assert (
        client.post(
            "/api/v1/inventory", json=body, headers={**ha, "Idempotency-Key": "bad-unit-001"}
        ).status_code
        == 422
    )


def test_idempotency_and_adjustment_version(client):
    _, token = account(client, "person")
    h = auth(token)
    item = create_ingredient(client, h)
    batch = stock(client, h, item)
    assert stock(client, h, item)["id"] == batch["id"]
    result = client.post(
        "/api/v1/inventory",
        json={"ingredient_id": item, "quantity": "200", "unit": "g"},
        headers={**h, "Idempotency-Key": "stock-001"},
    )
    assert result.status_code == 409
    changed = client.patch(
        f"/api/v1/inventory/{batch['id']}",
        json={"quantity": "90", "expected_version": 1},
        headers={**h, "Idempotency-Key": "adjust-001"},
    )
    assert changed.status_code == 200
    stale = client.patch(
        f"/api/v1/inventory/{batch['id']}",
        json={"quantity": "80", "expected_version": 1},
        headers={**h, "Idempotency-Key": "adjust-002"},
    )
    assert stale.status_code == 409
    assert quantities(client, h)[batch["id"]] == 90


def test_fefo_cook_and_repeated_undo(client):
    _, token = account(client, "person")
    h = auth(token)
    item = create_ingredient(client, h)
    late = stock(
        client, h, item, "100", "stock-late", (date.today() + timedelta(days=5)).isoformat()
    )
    early = stock(
        client, h, item, "50", "stock-early", (date.today() + timedelta(days=1)).isoformat()
    )
    rid = recipe(client, h, item)
    result = cook(client, h, rid)
    assert result.status_code == 201, result.text
    assert cook(client, h, rid).json()["id"] == result.json()["id"]
    assert quantities(client, h) == {late["id"]: Decimal(70), early["id"]: Decimal(0)}
    url = f"/api/v1/cooking/{result.json()['id']}/undo"
    for key in ("undo-001", "undo-001", "undo-002"):
        assert client.post(url, headers={**h, "Idempotency-Key": key}).status_code == 200
    assert quantities(client, h) == {late["id"]: Decimal(100), early["id"]: Decimal(50)}


def test_insufficient_and_expired_do_not_mutate(client):
    _, token = account(client, "person")
    h = auth(token)
    item = create_ingredient(client, h)
    batch = stock(client, h, item, "100", expires=(date.today() - timedelta(days=1)).isoformat())
    rid = recipe(client, h, item)
    assert cook(client, h, rid).status_code == 409
    assert quantities(client, h)[batch["id"]] == 100
    assert client.get("/api/v1/cooking", headers=h).json() == []
    with client.app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Operation)) == 1


def test_failure_after_record_insert_rolls_back(client):
    _, token = account(client, "person")
    h = auth(token)
    item = create_ingredient(client, h)
    batch = stock(client, h, item)
    rid = recipe(client, h, item)

    def fail(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("INSERT INTO COOKING_CONSUMPTIONS"):
            raise IntegrityError(statement, {}, RuntimeError("injected storage failure"))

    engine = client.app.state.engine
    event.listen(engine, "before_cursor_execute", fail)
    try:
        assert cook(client, h, rid).status_code == 409
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert quantities(client, h)[batch["id"]] == 100
    assert client.get("/api/v1/cooking", headers=h).json() == []
    assert cook(client, h, rid).status_code == 201


def test_composite_foreign_key_rejects_cross_user_reference(client):
    alice, ta = account(client, "alice")
    bob, _ = account(client, "bob")
    item = create_ingredient(client, auth(ta))
    with client.app.state.sessions() as db:
        db.add(InventoryBatch(user_id=bob["id"], ingredient_id=item, quantity=Decimal(10)))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


@pytest.mark.parametrize("same_key", [False, True])
def test_mysql_concurrent_cooking(client, same_key):
    if client.app.state.engine.dialect.name != "mysql":
        pytest.skip("Real MySQL required for concurrency evidence")
    _, token = account(client, "person")
    h = auth(token)
    item = create_ingredient(client, h)
    batch = stock(client, h, item)
    rid = recipe(client, h, item)
    gate = Barrier(2)

    def execute(n):
        gate.wait(timeout=10)
        return cook(client, h, rid, "race-same" if same_key else f"race-key-{n}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, [1, 2]))
    assert sorted(x.status_code for x in results) == ([201, 201] if same_key else [201, 409]), [
        x.text for x in results
    ]
    if same_key:
        assert results[0].json()["id"] == results[1].json()["id"]
    assert quantities(client, h)[batch["id"]] == 20
    assert len(client.get("/api/v1/cooking", headers=h).json()) == 1
