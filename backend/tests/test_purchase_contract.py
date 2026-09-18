import copy
import json
import tempfile
from pathlib import Path

import pytest
from app.core.config import Settings
from app.services.agent_model import ModelCallError, ModelCompletion
from scripts import purchase_contract
from scripts.purchase_contract import (
    IDS,
    PROTOCOL,
    BoundedModel,
    equal_number,
    load_protocol,
    registration,
    result_check,
    run_check,
    trial,
)


def spec(index):
    return load_protocol()["cases"][index]


class ContractModel:
    def __init__(self, case):
        self.case = case
        self.records = []

    def complete(self, messages, definitions):
        results = [json.loads(m["content"]) for m in messages if m.get("role") == "tool"]
        if not results:
            name, args = "get_inventory", {}
        elif "ingredients" in results[-1]:
            name, args = self.case["tool"], dict(self.case["arguments"])
            if name == "estimate_purchase":
                args["ingredient_id"] = next(i["id"] for i in results[-1]["ingredients"] if i["name"] == "大米")
        else:
            return {"content": "需补190克，整包买2包200克，预计6元。"}
        return {"tool_calls": [{"id": "test-call", "type": "function", "function": {
            "name": name, "arguments": json.dumps(args)}}]}


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("mode", ["fixed_workflow", "agent_tools"])
def test_real_services_match_contract_without_writes(client, index, mode):
    case = spec(index)
    report = trial(client, case, mode, ContractModel(case) if mode == "agent_tools" else None)
    assert report["objective_pass"] is True
    assert report["business_unchanged"]
    assert report["measurements"]["unauthorized_writes"]["count"] == 0
    assert report["actual_requests"] == 0  # Scripted models are not real provider calls.
    assert report["human_clarity"] is None and report["task_success"] is None
    assert report["measurements"]["required_query"]["satisfied"] is (True if mode == "agent_tools" else None)
    assert not hasattr(client.app.state, "evaluation_observer")


@pytest.mark.parametrize("index", [0, 1])
def test_wrong_results_and_missing_run_evidence_are_rejected(client, index):
    case = spec(index)
    report = trial(client, case, "fixed_workflow")
    before, payload = report["before"], report["output"]
    def line(value):
        return value if index == 0 else next(c for c in value["candidates"]
                                            if c["recipe"]["name"] == "白米饭")["shopping"][0]
    for key, value in (("estimated_cost", "5.70"), ("packages", 1), ("packages", True),
                       ("purchase_quantity", "190"), ("observed_on", "2000-01-01"),
                       ("source", "invented"), ("price_status", "unknown"),
                       ("shortage_quantity" if index == 0 else "missing_quantity", "140")):
        bad = copy.deepcopy(payload)
        line(bad)[key] = value
        assert not result_check(case, bad, before), key
    bad = copy.deepcopy(payload)
    if index == 0:
        bad["ingredient"]["id"] = "another-user"
    else:
        bad["constraints"]["servings"] = 1
    assert not result_check(case, bad, before)
    if index == 1:
        bad = copy.deepcopy(payload)
        target = next(c for c in bad["candidates"] if c["recipe"]["name"] == "白米饭")
        target["required_ingredients"][0]["quantity"] = "80"
        assert not result_check(case, bad, before)
        reduced = copy.deepcopy(payload)
        reduced["candidates"] = [c for c in reduced["candidates"] if c["recipe"]["name"] == "白米饭"]
        assert result_check(case, reduced, before)  # No hidden three-recipe requirement.
    args = dict(case["arguments"])
    if index == 0:
        args["ingredient_id"] = before["quotes"][0]["ingredient_id"]
    run = {"status": "completed", "pending": None, "result": {"message": "结果"},
           "events": [{"tool": case["tool"], "arguments": args, "result": payload}]}
    assert run_check(case, run, before)
    mutations = [lambda r: r.update(events=[]), lambda r: r.update(status="failed"),
                 lambda r: r.update(result={"message": ""}), lambda r: r.update(pending={"id": "x"}),
                 lambda r: r["events"][0].update(result={"error": {"code": "NOT_FOUND"}}),
                 lambda r: r["events"].append({"tool": "prepare_inventory", "result": {}}),
                 lambda r: r["events"][0]["arguments"].update(servings=1)]
    for mutate in mutations:
        bad = copy.deepcopy(run)
        mutate(bad)
        assert not run_check(case, bad, before)


@pytest.mark.parametrize("index", [0, 1])
def test_direct_uses_snapshot_without_tool_or_oracle_and_stays_unscored(client, index):
    class Direct:
        records = []

        def complete(self, messages, definitions):
            assert definitions == []
            assert "190" in messages[-1]["content"] if index == 0 else "三个人" in messages[-1]["content"]
            assert '"quantity": "50.000"' in messages[-1]["content"]
            assert '"default_servings": 1' in messages[-1]["content"]
            assert "expected" not in messages[-1]["content"]
            return {"content": "可能是5.70元。"}  # An incorrect nonempty answer cannot auto-pass.
    report = trial(client, spec(index), "direct_model", Direct())
    assert report["objective_pass"] is None and report["task_success"] is None
    assert report["measurements"]["required_query"]["satisfied"] is None
    assert report["business_unchanged"]


@pytest.mark.parametrize("output", [{"content": ""}, {"content": "2包", "tool_calls": [{}]}])
def test_direct_empty_or_tool_response_fails(client, output):
    class Direct:
        records = []

        def complete(self, messages, definitions):
            return output
    assert trial(client, spec(0), "direct_model", Direct())["objective_pass"] is False


def test_direct_timeout_keeps_failure_and_cleans_observer(client):
    class Direct:
        records = []

        def complete(self, messages, definitions):
            raise ModelCallError(503, "MODEL_UNAVAILABLE", "timeout", {})
    report = trial(client, spec(0), "direct_model", Direct())
    assert report["objective_pass"] is False and report["error_code"] == "MODEL_UNAVAILABLE"
    assert report["business_unchanged"] and not hasattr(client.app.state, "evaluation_observer")


def test_protocol_is_pinned_and_registration_has_six_bounded_slots(tmp_path):
    data = load_protocol()
    registered = registration(data, Settings(_env_file=None))
    assert len(registered["slots"]) == 6
    assert sum(s["max_requests"] for s in registered["slots"]) == 18
    assert {s["scenario"] for s in registered["slots"]} == set(IDS)
    assert len(registered["frozen_json_sha256"]) == 7
    assert "model_api_key" not in registered
    path = tmp_path / "changed.json"
    path.write_bytes(PROTOCOL.read_bytes().replace(b'"max_requests": 18', b'"max_requests": 19'))
    with pytest.raises(ValueError, match="Unsupported purchase contract"):
        load_protocol(path)


def test_request_cap_counts_attempts_before_provider_and_preserves_input(tmp_path):
    class Provider:
        calls = 0

        def complete_with_metadata(self, messages, definitions):
            self.calls += 1
            return ModelCompletion({"content": "ok"}, {"test": True})
    provider = Provider()
    model = BoundedModel(provider, tmp_path, 1)
    model.complete([{"role": "user", "content": "test"}], [])
    with pytest.raises(RuntimeError, match="request limit"):
        model.complete([], [])
    assert provider.calls == 1 and len(model.records) == 1
    assert (tmp_path / "call-01-input.json").exists()
    assert not (tmp_path / "call-02-attempt.json").exists()


def test_batch_records_all_slots_before_requests_and_refuses_rerun(monkeypatch):
    calls = []
    with tempfile.TemporaryDirectory(prefix="purchase-contract-test-") as temporary:
        output = Path(temporary) / "synthetic-batch"
        class Provider:
            def __init__(self, settings):
                pass

            def complete_with_metadata(self, messages, definitions):
                registered = json.loads((output / "registration.json").read_text(encoding="utf-8"))
                assert len(registered["slots"]) == 6
                calls.append(1)
                content = " ".join(str(m.get("content", "")) for m in messages)
                case = spec(1 if spec(1)["prompt"] in content else 0)
                message = (ContractModel(case).complete(messages, definitions) if definitions
                           else {"content": "直接模型离线替身，不计真实成绩"})
                return ModelCompletion(message, {"synthetic": True})
        monkeypatch.setattr(purchase_contract, "ChatModel", Provider)
        monkeypatch.setattr(purchase_contract, "Settings", lambda: Settings(_env_file=None))
        monkeypatch.setattr("sys.argv", ["purchase_contract", "--send-model", "--output", str(output)])
        assert purchase_contract.main() == 0
        summary = json.loads((output / "execution-complete.json").read_text(encoding="utf-8"))
        assert len(summary["slots"]) == 6 and len(calls) == 8
        assert summary["task_success"] is None
        with pytest.raises(FileExistsError):
            purchase_contract.main()
        assert len(calls) == 8


@pytest.mark.parametrize("value", [None, True, "NaN", "Infinity", "wrong", {}, []])
def test_numeric_oracle_rejects_missing_and_nonfinite(value):
    assert not equal_number(value, "6")
