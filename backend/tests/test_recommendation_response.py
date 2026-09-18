from copy import deepcopy
from datetime import date, timedelta

import pytest
from app.services.recommendation_response import cooking_availability, render
from test_agent import Scripted, call, create, step
from test_food import quantities, stock
from test_planning import plan, setup


@pytest.mark.parametrize("candidate", [
    {}, {"can_cook_now": True},
    {"can_cook_now": False, "shopping": [], "budget_status": "not_requested"},
    {"can_cook_now": True, "shopping": [{}], "budget_status": "not_requested"},
    {"can_cook_now": True, "shopping": [], "budget_status": "unknown"},
])
def test_unknown_or_inconsistent_state_does_not_enable_preview(candidate):
    assert cooking_availability(candidate)["enabled"] is False


def test_mixed_candidates_keep_actions_scoped_to_recipe(client):
    h, item, _ = setup(client)
    result = plan(client, h)
    blocked = result["candidates"][0]
    ready = deepcopy(blocked)
    ready.update(recipe={**ready["recipe"], "id": "other", "name": "另一餐"},
                 can_cook_now=True, shopping=[])
    result["candidates"].append(ready)
    response = render(result)
    assert [a["prepare_cooking"]["enabled"] for a in response["next_actions"]] == [False, True]
    assert response["next_actions"][0]["recipe_id"] == blocked["recipe"]["id"]
    assert "先购买缺料并确认入库" in response["message"]
    assert "另一餐" in response["message"]


def test_wrong_model_followup_is_preserved_only_as_evidence_and_restore_is_stable(client):
    h, item, rid = setup(client)
    before = quantities(client, h)
    wrong = "库存不足，但现在可以生成做饭预览。"
    client.app.state.agent_model = Scripted(call("recommend_meal", {"servings": 3}), {"content": wrong})
    run_id = create(client, h)
    step(client, h, run_id)
    result = step(client, h, run_id)
    assert result["status"] == "completed" and result["pending"] == {}
    assert result["result"]["model_message"] == wrong
    assert result["result"]["source_step"] == 1
    assert result["messages"][-1]["content"] == result["result"]["message"]
    assert wrong not in result["messages"][-1]["content"]
    assert "240.000克" in result["result"]["message"]
    assert not result["result"]["next_actions"][0]["prepare_cooking"]["enabled"]
    assert client.get(f"/api/v1/agent/runs/{run_id}", headers=h).json() == result
    assert quantities(client, h) == before
    # The rendered suggestion grants no execution permission: direct previews still validate stock.
    from app.services.agent import dispatch
    with client.app.state.sessions() as db:
        from app.models.agent import AgentRun
        owner = db.get(AgentRun, run_id).user_id
        error, pending = dispatch(db, owner, "prepare_cooking", {"recipe_id": rid, "servings": 3})
        assert error["error"]["code"] == "INSUFFICIENT_STOCK" and pending is None
    stock(client, h, item, qty="300")
    client.app.state.agent_model = Scripted(call("recommend_meal", {}), {"content": wrong})
    child = client.post("/api/v1/agent/runs", headers={**h, "Idempotency-Key": "next-response-01"},
                        json={"message": "重新查询", "parent_run_id": run_id}).json()
    step(client, h, child["id"])
    final = step(client, h, child["id"])
    assert final["result"]["next_actions"][0]["prepare_cooking"]["enabled"]
    assert final["result"]["next_actions"][0]["servings"] == 3
    old = client.get(f"/api/v1/agent/runs/{run_id}", headers=h).json()
    assert old["result"] == result["result"] and old["messages"] == result["messages"]


def test_failed_new_query_never_reuses_successful_recommendation(client):
    h, _, _ = setup(client)
    client.app.state.agent_model = Scripted(call("recommend_meal", {}),
        call("recommend_meal", {"servings": "invalid"}), {"content": "查询失败，需要修正条件。"})
    rid = create(client, h)
    step(client, h, rid)
    step(client, h, rid)
    final = step(client, h, rid)
    assert final["result"] == {"message": "查询失败，需要修正条件。"}


def test_empty_candidates_and_latest_constraints(client):
    h, _, _ = setup(client)
    result = render(plan(client, h, {"max_minutes": 1, "servings": 2}))
    assert result["next_actions"] == []
    assert "没有符合当前条件" in result["message"]
    assert "用时超过限制" in result["message"]
    assert "2人份，用时上限1分钟" in result["message"]


@pytest.mark.parametrize("age", [0, 31])
def test_package_cost_and_source_are_preserved_without_inventing_stale_prices(client, age):
    h, item, _ = setup(client)
    observed = (date.today() - timedelta(days=age)).isoformat()
    result = render(plan(client, h, {"servings": 3, "budget": "10", "quotes": [{
        "ingredient_id": item, "package_quantity": "100", "package_price": "3",
        "source": "测试报价", "observed_on": observed}]}))
    assert "测试报价" in result["message"] and observed in result["message"]
    assert not result["next_actions"][0]["prepare_cooking"]["enabled"]
    if age == 0:
        assert "3包，共300" in result["message"] and "预计9" in result["message"]
    else:
        assert "报价过期" in result["message"] and "预计9" not in result["message"]
