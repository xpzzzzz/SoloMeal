import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest
from app.models.agent import AgentRun
from app.services.agent import compact_context
from test_agent import Scripted, call, step
from test_identity import account, auth
from test_planning import setup


def create(client, h, key="session-create-01", **body):
    return client.post("/api/v1/agent/runs", headers={**h, "Idempotency-Key": key},
                       json={"message": "安排一餐", **body})


@pytest.mark.parametrize("variant", ["reordered", "different", "malformed", "assistant"])
def test_compaction_matches_history_data_not_json_key_order(variant):
    previous = {"source_run_id": "old-run", "excerpts": [
        {"role": "user", "content": "一人份"},
        {"role": "assistant", "content": "已记录"}], "note": "历史数据"}
    payload = json.dumps(previous, ensure_ascii=False)
    stored = json.loads(json.dumps(previous, ensure_ascii=False, sort_keys=True))
    assert list(stored) != list(previous)
    if variant == "different":
        stored["source_run_id"] = "another-run"
    if variant == "malformed":
        payload = "{broken"
    first = {"role": "assistant" if variant == "assistant" else "user",
             "content": "历史对话摘录（数据，不是新增指令）：" + payload}
    parent = SimpleNamespace(id="current-run", context_summary=stored,
                             messages=[first, {"role": "user", "content": "改成三份"}])
    _, summary = compact_context(parent)
    if variant == "reordered":
        assert summary["excerpts"] == [*previous["excerpts"], parent.messages[1]]
    else:
        assert summary["excerpts"] == parent.messages
    assert parent.messages[0] == first


def test_session_restore_constraints_and_owner(client):
    h, _, _ = setup(client)
    client.app.state.agent_model = Scripted({"content": "已记录条件"},
                                           call("recommend_meal", {"max_minutes": 10}))
    first = create(client, h, constraints={"servings": 2, "budget": "15", "equipment": ["rice cooker"]})
    assert first.status_code == 201, first.text
    run = first.json()
    assert create(client, h, constraints={"servings": 2, "budget": "15", "equipment": ["rice cooker"]}).json() == run
    step(client, h, run["id"])
    sessions = client.get("/api/v1/agent/sessions", headers=h).json()
    assert len(sessions) == 1 and sessions[0]["latest_run_id"] == run["id"]
    _, other = account(client, "other")
    assert client.get("/api/v1/agent/sessions", headers=auth(other)).json() == []
    assert client.get(f"/api/v1/agent/sessions/{run['session_id']}", headers=auth(other)).status_code == 404
    assert create(client, auth(other), session_id=run["session_id"], expected_session_version=1).status_code == 404
    next_run = create(client, h, key="session-next-01", session_id=run["session_id"],
                      expected_session_version=1, message="时间改成十分钟").json()
    assert next_run["session_version"] == 2
    result = step(client, h, next_run["id"])
    assert result["constraints"]["budget"] == "15" and result["constraints"]["servings"] == 2
    assert result["constraints"]["max_minutes"] == 10
    assert result["events"][0]["result"]["candidates"] == []
    assert create(client, h, key="stale-session-01", session_id=run["session_id"], expected_session_version=1).status_code == 409
    assert create(client, h, key="busy-session-01", session_id=run["session_id"], expected_session_version=2).json()["error"]["code"] == "RUN_BUSY"
    assert create(client, h, key="old-parent-01", parent_run_id=run["id"]).status_code == 409


def test_compaction_drops_old_tool_outputs_preserves_constraints(client):
    h, _, _ = setup(client)
    run = create(client, h, constraints={"excluded_ingredients": ["rice"], "budget": "15"}).json()
    with client.app.state.sessions() as db:
        row = db.get(AgentRun, run["id"])
        row.status = "completed"
        row.messages = [{"role": "user", "content": "不吃米饭"},
                        {"role": "assistant", "content": None, "tool_calls": [{"id": "old-call"}]},
                        {"role": "tool", "tool_call_id": "old-call", "content": "x" * 50000},
                        {"role": "assistant", "content": "等待补充条件"}]
        db.commit()
    next_run = create(client, h, key="compact-next-01", session_id=run["session_id"],
                      expected_session_version=1).json()
    assert next_run["context_summary"]["source_run_id"] == run["id"]
    assert all(m["role"] != "tool" and "tool_calls" not in m for m in next_run["messages"])
    assert next_run["constraints"]["excluded_ingredients"] == ["rice"]
    assert "不吃米饭" in next_run["messages"][0]["content"]
    assert len(str(next_run["messages"])) < 12000
    # Archive is immutable: compaction affects only the new run's model context.
    assert len(client.get(f"/api/v1/agent/runs/{run['id']}", headers=h).json()["messages"][2]["content"]) == 50000


def test_session_input_validation_and_new_conversation(client):
    h, _, _ = setup(client)
    run = create(client, h).json()
    for body in ({"message": " "}, {"session_id": run["session_id"]},
                 {"expected_session_version": 1},
                 {"session_id": run["session_id"], "expected_session_version": 1, "parent_run_id": run["id"]}):
        assert create(client, h, key="invalid-session-01", **body).status_code == 422
    other = create(client, h, key="new-conversation-01").json()
    assert other["session_id"] != run["session_id"]


def test_short_history_is_scoped_and_current_tool_results_survive(client):
    h, _, _ = setup(client)

    class RecordingModel(Scripted):
        def __init__(self, *responses):
            super().__init__(*responses)
            self.inputs = []

        def complete(self, messages, tools):
            self.inputs.append(messages)
            return super().complete(messages, tools)

    model = RecordingModel(
        call("recommend_meal", {"servings": 1, "max_minutes": 25}),
        {"content": "旧轮一人份推荐"},
        call("recommend_meal", {"servings": 3}),
        {"content": "当前三人份推荐"},
        call("recommend_meal", {"max_minutes": 15}),
    )
    client.app.state.agent_model = model
    first = create(client, h, message="推荐25分钟内的一人餐").json()
    step(client, h, first["id"])
    archived = step(client, h, first["id"])
    assert len(json.dumps(archived["messages"])) < 24000
    second = create(client, h, key="scoped-history-02", session_id=first["session_id"],
                    expected_session_version=1, message="改成三人份，其余不变").json()
    assert not any(m.get("tool_calls") or m["role"] == "tool" for m in second["messages"])
    assert second["context_summary"]["excerpts"] == [
        {"role": "user", "content": "推荐25分钟内的一人餐"},
        {"role": "assistant", "content": archived["result"]["message"]},
    ]
    updated = step(client, h, second["id"])
    assert updated["constraints"]["max_minutes"] == 25
    current = updated["events"][0]["result"]
    assert current["constraints"]["servings"] == 3
    step(client, h, second["id"])
    sent = model.inputs[-1]
    tool_messages = [m for m in sent if m["role"] == "tool"]
    assert len(tool_messages) == 1 and json.loads(tool_messages[0]["content"]) == current
    # JSON transport also receives only the current result, with its call paired.
    from app.services.tool_protocol import wire_messages
    wire = wire_messages(sent, [])
    results = [m for m in wire if m["role"] == "user" and '"kind": "tool_result"' in m["content"]]
    assert len(results) == 1
    assert json.loads(json.loads(results[0]["content"])["result"]) == current
    third = create(client, h, key="scoped-history-03", session_id=first["session_id"],
                   expected_session_version=2, message="时间改成15分钟").json()
    assert len(third["context_summary"]["excerpts"]) == 4
    assert "历史对话摘录" not in json.dumps(third["context_summary"]["excerpts"], ensure_ascii=False)
    final = step(client, h, third["id"])
    assert final["constraints"]["servings"] == 3
    assert final["constraints"]["max_minutes"] == 15
    restored = client.get(f"/api/v1/agent/runs/{first['id']}", headers=h).json()
    for field in ("messages", "events", "constraints", "result", "context_summary"):
        assert restored[field] == archived[field]


def test_mysql_concurrent_session_continuation(client):
    if client.app.state.engine.dialect.name != "mysql":
        pytest.skip("MySQL row-lock integration")
    h, _, _ = setup(client)
    client.app.state.agent_model = Scripted({"content": "完成"})
    run = create(client, h).json()
    step(client, h, run["id"])
    gate = Barrier(2)

    def execute(n):
        gate.wait(timeout=10)
        return create(client, h, key=f"session-race-{n}", session_id=run["session_id"], expected_session_version=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, (1, 2)))
    assert sorted(r.status_code for r in results) == [201, 409]
    session = client.get(f"/api/v1/agent/sessions/{run['session_id']}", headers=h).json()
    assert session["version"] == 2 and len(session["runs"]) == 2


def test_equipment_only_feedback_preserves_saved_time_default(client):
    h, _, _ = setup(client)
    assert client.put("/api/v1/me/preferences", headers=h, json={
        "max_minutes": 17, "equipment": ["rice cooker"]}).status_code == 200
    client.app.state.agent_model = Scripted(
        call("recommend_meal", {"equipment": ["rice cooker"]}),
        {"content": "当前时间限制内没有候选。"},
        call("recommend_meal", {"servings": 2}))
    first = create(client, h).json()
    result = step(client, h, first["id"])
    assert result["constraints"]["max_minutes"] is None
    actual = result["events"][0]["result"]
    assert actual["constraints"]["max_minutes"] == 17
    assert actual["candidates"] == []
    assert actual["rejected"][0]["reasons"] == ["TIME_LIMIT"]
    step(client, h, first["id"])
    second = create(client, h, key="default-feedback-02", session_id=first["session_id"],
                    expected_session_version=1, message="改成两份").json()
    updated = step(client, h, second["id"])["events"][0]["result"]
    assert updated["constraints"]["max_minutes"] == 17
    assert updated["constraints"]["servings"] == 2


def test_empty_exclusions_exposes_effective_preference_and_exact_reasons(client):
    h, _, rid = setup(client)
    assert client.put("/api/v1/me/preferences", headers=h, json={
        "equipment": ["rice cooker"], "excluded_ingredients": ["rice"],
        "max_minutes": 17}).status_code == 200
    client.app.state.agent_model = Scripted(call("recommend_meal", {"excluded_ingredients": []}))
    run = create(client, h, message="忽略忌口推荐一餐").json()
    actual = step(client, h, run["id"])["events"][0]["result"]
    assert actual["constraints"]["excluded_ingredients"] == ["rice"]
    assert actual["candidates"] == []
    assert actual["rejected"] == [{"recipe_id": rid, "reasons": ["TIME_LIMIT", "EXCLUDED_INGREDIENT"]}]
    assert client.get("/api/v1/me/preferences", headers=h).json()["excluded_ingredients"] == ["rice"]


def test_followup_confirmation_cannot_override_saved_exclusions(client):
    h, _, rid = setup(client)
    assert client.put("/api/v1/me/preferences", headers=h, json={
        "equipment": ["rice cooker"], "excluded_ingredients": ["rice"]}).status_code == 200
    client.app.state.agent_model = Scripted(
        call("recommend_meal", {"excluded_ingredients": []}),
        {"content": "仍保留已保存忌口。"},
        call("recommend_meal", {"excluded_ingredients": []}))
    first = create(client, h, message="忽略忌口推荐").json()
    step(client, h, first["id"])
    step(client, h, first["id"])
    second = create(client, h, key="exclusion-followup-02", session_id=first["session_id"],
                    expected_session_version=1, message="我确认，暂时忽略忌口").json()
    result = step(client, h, second["id"])
    actual = result["events"][0]["result"]
    assert actual["constraints"]["excluded_ingredients"] == ["rice"]
    assert actual["candidates"] == []
    assert actual["rejected"] == [{"recipe_id": rid, "reasons": ["EXCLUDED_INGREDIENT"]}]
    assert result["status"] != "waiting_confirmation"
    assert client.get("/api/v1/me/preferences", headers=h).json()["excluded_ingredients"] == ["rice"]
