from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from test_food import cook, stock
from test_identity import account, auth
from test_planning import setup
from test_plans import confirm, create


def archive(client, h, batch, version=1, value=True, key="archive-batch-01"):
    return client.post(f"/api/v1/inventory/{batch['id']}/archive", headers={
        **h, "Idempotency-Key": key,
    }, json={"expected_version": version, "archived": value})


def update_body(client, h, rid):
    row = client.get(f"/api/v1/recipes/{rid}", headers=h).json()
    return {
        **{k: row[k] for k in ("name", "servings", "minutes", "equipment", "steps", "source")},
        "expected_version": row["version"],
        "ingredients": [{k: line[k] for k in ("ingredient_id", "quantity", "unit", "optional")}
                        for line in row["ingredients"]],
    }


def test_archive_restore_replay_and_isolation(client):
    h, item, rid = setup(client)
    batch = stock(client, h, item)
    plan = create(client, h, rid)
    _, token = account(client, "other")
    other = auth(token)
    assert archive(client, other, batch).status_code == 404
    assert client.get(f"/api/v1/inventory/{batch['id']}", headers=other).status_code == 404
    result = archive(client, h, batch)
    assert result.status_code == 200, result.text
    assert result.json()["archived"] and result.json()["version"] == 2
    assert archive(client, h, batch).json() == result.json()
    assert archive(client, h, batch, value=False).status_code == 409
    assert client.get("/api/v1/inventory", headers=h).json() == []
    rows = client.get("/api/v1/inventory?include_archived=true", headers=h).json()
    assert len(rows) == 1 and Decimal(rows[0]["quantity"]) == 100
    candidate = client.post("/api/v1/recommendations", headers=h, json={}).json()["candidates"][0]
    assert not candidate["can_cook_now"]
    assert cook(client, h, rid).json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert confirm(client, h, plan).json()["error"]["code"] == "PLAN_STALE"
    assert client.patch(f"/api/v1/inventory/{batch['id']}", headers={
        **h, "Idempotency-Key": "adjust-archived",
    }, json={"quantity": "50", "expected_version": 2}).json()["error"]["code"] == "BATCH_ARCHIVED"
    assert archive(client, h, batch, value=False, key="restore-stale").status_code == 409
    restored = archive(client, h, batch, 2, False, "restore-current")
    assert restored.status_code == 200 and restored.json()["version"] == 3
    events = client.get("/api/v1/inventory/events", headers=h).json()
    assert [e["reason"] for e in events] == ["purchase", "archive", "restore"]
    assert sum(Decimal(e["delta"]) for e in events) == 100


def test_undo_restores_archived_batch_without_reactivating(client):
    h, item, rid = setup(client)
    batch = stock(client, h, item)
    record = cook(client, h, rid).json()
    assert archive(client, h, batch, 2).status_code == 200
    for key in ("undo-archive-01", "undo-archive-01", "undo-archive-02"):
        assert client.post(f"/api/v1/cooking/{record['id']}/undo", headers={
            **h, "Idempotency-Key": key,
        }).status_code == 200
    row = client.get(f"/api/v1/inventory/{batch['id']}", headers=h).json()
    assert row["archived"] and row["version"] == 4 and Decimal(row["quantity"]) == 100


def test_batch_metadata_and_validation(client):
    h, item, rid = setup(client)
    batch = stock(client, h, item)
    plan = create(client, h, rid)
    path = f"/api/v1/inventory/{batch['id']}"
    headers = {**h, "Idempotency-Key": "metadata-change"}
    for body in ({}, {"quantity": None}, {"quantity": "-1"}, {"location": " "},
                 {"expires_on": "2030-01-01"}, {"expiry_source": "user"},
                 {"expires_on": None, "expiry_source": "user"}, {"archived": True}):
        assert client.patch(path, headers=headers, json={"expected_version": 1, **body}).status_code == 422
    body = {"expected_version": 1, "location": "冷冻", "expires_on": "2030-01-01", "expiry_source": "package"}
    result = client.patch(path, headers=headers, json=body)
    assert result.status_code == 200, result.text
    assert result.json()["location"] == "冷冻" and Decimal(result.json()["quantity"]) == 100
    assert client.patch(path, headers=headers, json=body).json() == result.json()
    assert confirm(client, h, plan).json()["error"]["code"] == "PLAN_STALE"
    result = client.patch(path, headers={**h, "Idempotency-Key": "metadata-clear"}, json={
        "expected_version": 2, "expires_on": None, "expiry_source": "unknown",
    })
    assert result.status_code == 200 and result.json()["expiry_status"] == "unknown"


def test_recipe_edit_delete_preserves_history_and_stales_plan(client):
    h, item, rid = setup(client)
    stock(client, h, item, "300")
    cooked = cook(client, h, rid).json()
    plan = create(client, h, rid)
    body = update_body(client, h, rid)
    body.update(name="new bowl", steps=["Different steps"])
    path = f"/api/v1/recipes/{rid}"
    headers = {**h, "Idempotency-Key": "recipe-edit-01"}
    _, token = account(client, "other")
    assert client.put(path, headers={**auth(token), "Idempotency-Key": "recipe-edit-01"}, json=body).status_code == 404
    result = client.put(path, headers=headers, json=body)
    assert result.status_code == 200 and result.json()["version"] == 2, result.text
    assert client.put(path, headers=headers, json=body).json() == result.json()
    assert client.put(path, headers={**h, "Idempotency-Key": "recipe-edit-stale"}, json=body).status_code == 409
    assert confirm(client, h, plan).json()["error"]["code"] == "PLAN_STALE"
    headers = {**h, "Idempotency-Key": "recipe-delete-01"}
    assert client.request("DELETE", path, headers=headers, json={"expected_version": 1}).status_code == 409
    for _ in range(2):
        assert client.request("DELETE", path, headers=headers, json={"expected_version": 2}).status_code == 200
    assert client.get(path, headers=h).status_code == 404
    assert client.get("/api/v1/recipes", headers=h).json() == []
    assert confirm(client, h, plan).json()["error"]["code"] == "PLAN_STALE"
    history = client.get("/api/v1/cooking", headers=h).json()
    assert history[0]["recipe"] == cooked["recipe"]
    assert client.post(f"/api/v1/cooking/{cooked['id']}/undo", headers={
        **h, "Idempotency-Key": "undo-deleted-recipe",
    }).status_code == 200


def test_recipe_edit_failure_rolls_back_lines(client):
    h, _, rid = setup(client)
    path = f"/api/v1/recipes/{rid}"
    before = client.get(path, headers=h).json()
    body = update_body(client, h, rid)
    body["name"] = "should roll back"

    def fail(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("INSERT INTO RECIPE_INGREDIENTS"):
            raise IntegrityError(statement, {}, RuntimeError("injected failure"))

    engine = client.app.state.engine
    event.listen(engine, "before_cursor_execute", fail)
    try:
        result = client.put(path, headers={**h, "Idempotency-Key": "edit-rollback-01"}, json=body)
        assert result.status_code == 409
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert client.get(path, headers=h).json() == before


def test_mysql_archive_cooking_race(client):
    if client.app.state.engine.dialect.name != "mysql":
        pytest.skip("MySQL row-lock integration")
    h, item, rid = setup(client)
    batch = stock(client, h, item)
    gate = Barrier(2)

    def run(n):
        gate.wait(timeout=10)
        return archive(client, h, batch) if n == 0 else cook(client, h, rid)

    with ThreadPoolExecutor(max_workers=2) as pool:
        archived, cooked = list(pool.map(run, (0, 1)))
    assert (archived.status_code, cooked.status_code) in ((200, 409), (409, 201))
    row = client.get(f"/api/v1/inventory/{batch['id']}", headers=h).json()
    assert row["version"] == 2
    assert Decimal(row["quantity"]) == (100 if row["archived"] else 20)
