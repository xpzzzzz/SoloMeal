import json

import pytest
from scripts.review_agent import entry, main, score


def trial(tmp_path, mode="agent_tools", scenario="A018", objective=True):
    directory = tmp_path / (mode + scenario)
    directory.mkdir()
    (directory / "attempt.json").write_text(json.dumps({"scenario": scenario, "mode": mode}), encoding="utf-8")
    (directory / "report.json").write_text(json.dumps({
        "scenario_id": scenario, "mode": mode, "objective_pass": objective,
        "business_unchanged": True, "output": {"message": "没有付款工具"},
    }), encoding="utf-8")
    return directory


def rate(item, value=True, kind="codex"):
    item["reviewer"] = {"kind": kind, "name": "test reviewer"}
    for criterion in item["criteria"].values():
        criterion.update(passed=value, evidence=[{
            "file": "report.json", "pointer": "/output/message", "reason": "test evidence",
        }])
    return item


def test_safety_alone_is_not_task_success(tmp_path):
    item = entry(trial(tmp_path))
    assert score(item)["task_success"] is None
    assert score(rate(item))["task_success"] is True
    item["criteria"]["faithfulness"]["passed"] = False
    assert score(item)["task_success"] is False


def test_transport_failure_cannot_be_overridden_by_semantics(tmp_path):
    item = rate(entry(trial(tmp_path, objective=False)))
    assert score(item)["task_success"] is False


def test_missing_report_stays_failed_and_later_completion_invalidates_binding(tmp_path):
    directory = trial(tmp_path)
    raw = (directory / "report.json").read_bytes()
    (directory / "report.json").unlink()
    item = entry(directory)
    assert score(item)["status"] == "failed"
    assert score(item)["missing_report"] is True
    (directory / "report.json").write_bytes(raw)
    with pytest.raises(ValueError, match="changed"):
        score(item)


@pytest.mark.parametrize("scenario", ["A010", "A011", "A012", "A016", "A019", "A020"])
def test_direct_model_never_claims_execution(tmp_path, scenario):
    item = rate(entry(trial(tmp_path, "direct_model", scenario, None)))
    result = score(item)
    assert result["decision_success"] is True
    assert result["task_success"] is None and result["status"] == "not_applicable"


def test_direct_read_decision_and_fixed_intent_are_separate(tmp_path):
    direct = rate(entry(trial(tmp_path, "direct_model", "A001", None)))
    assert score(direct)["task_success"] is True
    fixed = entry(trial(tmp_path, "fixed_workflow"))
    assert score(fixed)["task_success"] is True
    assert score(fixed)["comparison_scope"] == "known_structured_intent"
    with pytest.raises(ValueError, match="fixed intent"):
        score(rate(fixed))


def test_clarity_cannot_be_filled_by_codex(tmp_path):
    item = rate(entry(trial(tmp_path)))
    item["human_clarity"] = 5
    item["clarity_evidence"] = item["criteria"]["intent"]["evidence"]
    with pytest.raises(ValueError, match="human reviewer"):
        score(item)
    item["reviewer"]["kind"] = "human"
    assert score(item)["human_clarity"] == 5
    item["human_clarity"] = True
    with pytest.raises(ValueError, match="integer"):
        score(item)


def test_ratings_require_resolving_evidence_and_strict_boolean(tmp_path):
    item = rate(entry(trial(tmp_path)))
    item["criteria"]["intent"]["passed"] = 1
    with pytest.raises(ValueError, match="booleans"):
        score(item)
    item["criteria"]["intent"]["passed"] = True
    item["criteria"]["intent"]["evidence"][0]["pointer"] = "/absent"
    with pytest.raises(ValueError, match="does not resolve"):
        score(item)


def test_amendments_applied_without_modifying_catalog(tmp_path):
    assert "all three" in entry(trial(tmp_path, scenario="A005"))["rubric"]["oracle"]
    assert entry(trial(tmp_path, scenario="A007"))["rubric"]["fixture"] == "low_stock"


def test_cli_retains_denominator_and_does_not_pool_versions(tmp_path):
    a = trial(tmp_path)
    b = trial(tmp_path, scenario="A014", objective=False)
    review = tmp_path / "review.json"
    output = tmp_path / "score.json"
    main(["init", "--trial", str(a), "--trial", str(b), "--output", str(review)])
    main(["score", "--review", str(review), "--output", str(output)])
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["scheduled_trials"] == 2
    assert result["counts"] == {"passed": 0, "failed": 1, "unscored": 1, "not_applicable": 0}
    assert result["pooled_success_rate"] is None and result["p8_gate"] == "incomplete"
    with pytest.raises(FileExistsError):
        main(["score", "--review", str(review), "--output", str(output)])
    data = json.loads(review.read_text(encoding="utf-8"))
    data["trials"].pop()
    review.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="retained"):
        main(["score", "--review", str(review), "--output", str(tmp_path / "bad.json")])


def test_raw_response_tampering_rejected(tmp_path):
    directory = trial(tmp_path)
    result = directory / "call-01-result.json"
    result.write_text("{}", encoding="utf-8")
    item = entry(directory)
    result.write_text('{"changed": true}', encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        score(item)
