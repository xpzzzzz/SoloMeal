import json
from uuid import uuid4

import pytest
from app.services.agent import dispatch
from test_agent import action, call, create, step
from test_identity import account, auth
from test_planning import setup

FAKE_QUOTE = {"ingredient_id": "11111111-1111-1111-1111-111111111111", "package_quantity": "100",
              "package_price": "3", "source": "shop", "observed_on": "2026-01-01"}


@pytest.mark.parametrize("name,args,lookup", [
    ("prepare_inventory", {"ingredient_id": "rice", "quantity": "125", "unit": "g"}, "get_inventory"),
    ("prepare_cooking", {"recipe_id": "rice", "servings": 2}, "list_recipes"),
    ("prepare_undo", {"cooking_id": "yesterday"}, "get_cooking_history"),
    ("propose_plan", {"recipe_id": "rice"}, "list_recipes"),
    ("estimate_purchase", {"ingredient_id": "rice", "quantity": "190", "unit": "g"}, "get_inventory"),
])
def test_invalid_id_exposes_only_read_only_recovery(name, args, lookup):
    result, pending = dispatch(None, "unused", name, args)
    assert pending is None
    error = result["error"]
    assert error["code"] == "INVALID_TOOL_ARGUMENTS"
    assert error["recovery"]["tool"] == lookup
    assert error["recovery"]["arguments"] == {}
    assert "rice" not in json.dumps(error) and "yesterday" not in json.dumps(error)


@pytest.mark.parametrize("name,args", [
    ("recommend_meal", {"quotes": [FAKE_QUOTE]}),
    ("propose_plan", {"recipe_id": FAKE_QUOTE["ingredient_id"], "constraints": {"quotes": [FAKE_QUOTE]}}),
])
def test_price_facts_are_not_model_input(name, args):
    result, pending = dispatch(None, "unused", name, args)
    assert pending is None
    error = result["error"]
    assert error["code"] == "INVALID_TOOL_ARGUMENTS" and "recovery" not in error
    assert [e["type"] for e in error["fields"]] == ["extra_forbidden"]
    assert error["fields"][0]["location"][-1] == "unknown_field"
    assert "2026-01-01" not in json.dumps(error) and "shop" not in json.dumps(error)


def test_quantity_error_does_not_suggest_id_recovery():
    result, pending = dispatch(None, "unused", "prepare_inventory", {
        "ingredient_id": str(uuid4()), "quantity": "a little", "unit": "g"})
    assert pending is None and "recovery" not in result["error"]
    assert "a little" not in json.dumps(result)


@pytest.mark.parametrize("target", ["invalid", "missing", "foreign"])
def test_lookup_recovery_preview_cancel_never_writes_or_leaks_other_owner(client, target):
    h, item, _ = setup(client)
    _, token = account(client, "foreign_recovery")
    other = auth(token)
    foreign = client.post("/api/v1/ingredients", headers=other,
                          json={"name": "private ingredient", "unit": "g"}).json()["id"]
    identifier = {"invalid": "rice", "missing": str(uuid4()), "foreign": foreign}[target]

    class Recovering:
        def complete(self, messages, tools):
            results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
            if not results:
                return call("prepare_inventory", {"ingredient_id": identifier,
                                                  "quantity": "125", "unit": "g"})
            if "error" in results[-1]:
                recovery = results[-1]["error"]["recovery"]
                return call(recovery["tool"], recovery["arguments"])
            assert results[-1]["batches"] == []
            assert {i["id"] for i in results[-1]["ingredients"]} == {item}
            return call("prepare_inventory", {"ingredient_id": results[-1]["ingredients"][0]["id"],
                                              "quantity": "125", "unit": "g"})

    client.app.state.agent_model = Recovering()
    rid = create(client, h)
    failed = step(client, h, rid)
    assert failed["status"] == "ready" and failed["pending"] == {}
    assert failed["events"][0]["arguments"] == {}
    assert "private ingredient" not in json.dumps(failed)
    assert step(client, h, rid)["status"] == "ready"
    preview = step(client, h, rid)
    assert preview["status"] == "awaiting_confirmation"
    assert preview["pending"]["request"]["ingredient_id"] == item
    assert preview["pending"]["preview"]["quantity"] == "125"
    assert action(client, h, rid, "cancel").json()["status"] == "cancelled"
    assert action(client, h, rid, "approve").status_code == 409
    assert client.get("/api/v1/inventory", headers=h).json() == []
    assert client.get("/api/v1/inventory", headers=other).json() == []
