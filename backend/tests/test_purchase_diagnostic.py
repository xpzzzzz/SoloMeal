import copy
import json

import pytest
from scripts.diagnose_purchase import PROTOCOL, purchase_check, purchase_trial


class PurchaseModel:
    records = []

    def complete(self, messages, definitions):
        results = [json.loads(m["content"]) for m in messages if m.get("role") == "tool"]
        if not results:
            name, args = "get_inventory", {}
        elif "ingredients" in results[-1]:
            rice = next(i for i in results[-1]["ingredients"] if i["name"] == "大米")
            name, args = "estimate_purchase", {
                "ingredient_id": rice["id"], "quantity": "190", "unit": "g", "budget": "6"}
        else:
            return {"content": "按保存报价，需2包，共200克，预计6元，在预算内。"}
        return {"tool_calls": [{"id": "call-test", "type": "function", "function": {
            "name": name, "arguments": json.dumps(args)}}]}


def test_new_shape_driver_uses_real_tools_and_preserves_business(client):
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    report = purchase_trial(client, PurchaseModel(), protocol)
    assert report["objective_pass"]
    assert report["business_unchanged"]
    assert report["measurements"]["unauthorized_writes"]["count"] == 0
    assert report["measurements"]["required_query"]["satisfied"] is True
    assert [e["tool"] for e in report["output"]["events"]] == ["get_inventory", "estimate_purchase"]
    assert not hasattr(client.app.state, "evaluation_observer")


@pytest.mark.parametrize("mutation", ["wrong_cost", "wrong_id", "wrong_date", "no_tool", "pending"])
def test_new_shape_oracle_rejects_incorrect_or_missing_evidence(mutation):
    expected = json.loads(PROTOCOL.read_text(encoding="utf-8"))["new_shape"]["expected_result"]
    quote = {"ingredient_id": "rice", "source": "saved", "observed_on": "2026-09-14"}
    result = {**copy.deepcopy(expected), "ingredient": {"id": "rice"},
              "source": "saved", "observed_on": "2026-09-14"}
    run = {"status": "completed", "pending": None, "events": [{"tool": "estimate_purchase",
           "arguments": {"budget": "6"}, "result": result}]}
    assert purchase_check(run, quote, expected)
    if mutation == "wrong_cost":
        result["estimated_cost"] = "5.70"
    elif mutation == "wrong_id":
        result["ingredient"]["id"] = "egg"
    elif mutation == "wrong_date":
        result["observed_on"] = "2023-10-27"
    elif mutation == "no_tool":
        run["events"] = []
    else:
        run["pending"] = {"preview": {}}
    assert not purchase_check(run, quote, expected)
