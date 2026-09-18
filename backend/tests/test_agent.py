import json
from datetime import date, timedelta

from app.core.errors import AppError
from test_food import stock
from test_identity import account, auth
from test_planning import setup


class Scripted:
    def __init__(self, *responses):
        self.responses = list(responses)

    def complete(self, messages, tools):
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def call(name, args):
    return {
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ]
    }


def create(client, h):
    result = client.post(
        "/api/v1/agent/runs",
        headers={**h, "Idempotency-Key": "agent-create-01"},
        json={"message": "根据我的库存安排一餐"},
    )
    assert result.status_code == 201, result.text
    return result.json()["id"]


def step(client, h, rid):
    result = client.post(f"/api/v1/agent/runs/{rid}/advance", headers=h)
    assert result.status_code == 200, result.text
    return result.json()


def action(client, h, rid, name):
    return client.post(
        f"/api/v1/agent/runs/{rid}/{name}",
        headers={**h, "Idempotency-Key": "action-" + name + "-01"},
    )


def test_tool_loop_persistence_and_isolation(client):
    h, item, _ = setup(client)
    stock(client, h, item)
    client.app.state.agent_model = Scripted(
        call("get_inventory", {}), {"content": "已查询库存，请选择菜谱。"}
    )
    rid = create(client, h)
    first = step(client, h, rid)
    assert first["status"] == "ready" and first["events"][0]["result"]["batches"]
    assert step(client, h, rid)["status"] == "completed"
    assert client.get(f"/api/v1/agent/runs/{rid}", headers=h).json()["steps"] == 2
    _, other = account(client, "other")
    assert client.get(f"/api/v1/agent/runs/{rid}", headers=auth(other)).status_code == 404
    assert client.get("/api/v1/agent/runs", headers=auth(other)).json() == []


def test_inventory_expiry_survives_the_tool_boundary(client):
    h, item, _ = setup(client)
    expires = (date.today() + timedelta(days=3)).isoformat()
    batch = stock(client, h, item, key="stock-expiry-01", expires=expires)
    client.app.state.agent_model = Scripted(
        call("get_inventory", {}), {"content": "已查询库存，请选择菜谱。"}
    )
    rid = create(client, h)
    result = step(client, h, rid)["events"][0]["result"]
    row = next(b for b in result["batches"] if b["id"] == batch["id"])
    assert row["expires_on"] == expires and row["expiry_status"] == "expiring_soon"
    assert row["expires_on"] == next(
        b for b in client.get("/api/v1/inventory", headers=h).json() if b["id"] == batch["id"]
    )["expires_on"]
    assert step(client, h, rid)["status"] == "completed"


def test_proposal_requires_approval_and_never_cooks(client):
    h, item, recipe = setup(client)
    stock(client, h, item)
    client.app.state.agent_model = Scripted(call("propose_plan", {"recipe_id": recipe}))
    rid = create(client, h)
    result = step(client, h, rid)
    assert result["status"] == "awaiting_confirmation"
    assert client.get("/api/v1/plans", headers=h).json() == []
    approved = action(client, h, rid, "approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert action(client, h, rid, "approve").json() == approved.json()
    assert len(client.get("/api/v1/plans", headers=h).json()) == 1
    assert client.get("/api/v1/cooking", headers=h).json() == []


def test_bad_tool_arguments_and_forbidden_tool(client):
    h, _, _ = setup(client)
    client.app.state.agent_model = Scripted(
        call("get_inventory", {"user_id": "other"}), call("cook", {})
    )
    rid = create(client, h)
    assert step(client, h, rid)["events"][0]["result"]["error"]["code"] == "INVALID_TOOL_ARGUMENTS"
    assert step(client, h, rid)["events"][1]["result"]["error"]["code"] == "UNKNOWN_TOOL"
    assert client.get("/api/v1/cooking", headers=h).json() == []


def test_validation_feedback_identifies_types_without_reflecting_untrusted_input():
    from app.services.agent import dispatch

    result, pending = dispatch(None, "unused", "recommend_meal", {
        "max_minutes": "20", "servings": "private-value", "private-field": "secret"})
    error = result["error"]
    assert error["code"] == "INVALID_TOOL_ARGUMENTS" and pending is None
    assert {tuple(e["location"]): e["type"] for e in error["fields"]} == {
        ("max_minutes",): "int_type", ("servings",): "int_type", ("unknown_field",): "extra_forbidden"}
    assert "private" not in json.dumps(error) and "secret" not in json.dumps(error)
    assert "20" not in json.dumps(error, ensure_ascii=False)


def test_model_can_correct_integer_types_without_losing_constraints(client):
    h, _, _ = setup(client)
    client.app.state.agent_model = Scripted(
        call("recommend_meal", {"max_minutes": "20", "servings": "1"}),
        call("recommend_meal", {"max_minutes": 20, "servings": 1}),
        {"content": "已按原条件计算"})
    rid = create(client, h)
    assert step(client, h, rid)["events"][0]["result"]["error"]["fields"]
    corrected = step(client, h, rid)
    assert corrected["constraints"]["max_minutes"] == 20
    assert corrected["constraints"]["servings"] == 1
    assert step(client, h, rid)["status"] == "completed"


def test_failure_retry_and_cancel(client):
    h, _, _ = setup(client)
    client.app.state.agent_model = Scripted(
        AppError(502, "MODEL_UNAVAILABLE", "private upstream payload"), call("get_inventory", {})
    )
    rid = create(client, h)
    result = step(client, h, rid)
    assert result["status"] == "failed" and "private upstream" not in json.dumps(result)
    assert action(client, h, rid, "retry").status_code == 200
    assert step(client, h, rid)["status"] == "ready"
    assert action(client, h, rid, "cancel").json()["status"] == "cancelled"
    assert client.post(f"/api/v1/agent/runs/{rid}/advance", headers=h).status_code == 409


def test_stale_proposal_rejected(client):
    h, item, recipe = setup(client)
    client.app.state.agent_model = Scripted(call("propose_plan", {"recipe_id": recipe}))
    rid = create(client, h)
    step(client, h, rid)
    stock(client, h, item)
    result = action(client, h, rid, "approve")
    assert result.status_code == 409, result.text
    assert client.get("/api/v1/plans", headers=h).json() == []


def test_model_disabled_fails_without_network(client):
    h, _, _ = setup(client)
    assert step(client, h, create(client, h))["result"]["error"]["code"] == "MODEL_NOT_CONFIGURED"


def test_step_limit_and_malformed_arguments(client):
    h, _, _ = setup(client)
    malformed = call("get_inventory", {})
    malformed["tool_calls"][0]["function"]["arguments"] = "{broken"
    client.app.state.agent_model = Scripted(*([malformed] * 8))
    rid = create(client, h)
    for _ in range(8):
        assert step(client, h, rid)["status"] == "ready"
    result = step(client, h, rid)
    assert result["result"]["error"]["code"] == "STEP_LIMIT"
    assert len(result["events"]) == 8
    assert all(e["result"]["error"]["code"] == "INVALID_TOOL_ARGUMENTS" for e in result["events"])


def test_running_lease_blocks_duplicate_and_cancel_wins(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    entered, release = Event(), Event()

    class Waiting:
        def complete(self, messages, tools):
            entered.set()
            assert release.wait(15)
            return call("get_inventory", {})

    h, _, _ = setup(client)
    client.app.state.agent_model = Waiting()
    rid = create(client, h)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(step, client, h, rid)
        try:
            assert entered.wait(10)
            assert client.post(f"/api/v1/agent/runs/{rid}/advance", headers=h).status_code == 409
            assert action(client, h, rid, "retry").status_code == 409
            assert action(client, h, rid, "cancel").status_code == 200
        finally:
            release.set()
        result = future.result(timeout=15)
    assert result["status"] == "cancelled" and result["events"] == []
