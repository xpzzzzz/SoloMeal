import json

import pytest
from app.core.config import Settings
from scripts.purchase_contract import load_protocol, registration
from scripts.review_agent import digest, save
from scripts.review_purchase_contract import prepare, score_review


@pytest.fixture
def batch(tmp_path):
    registered = registration(load_protocol(), Settings(_env_file=None))
    save(tmp_path / "registration.json", registered)
    for slot in registered["slots"]:
        directory = tmp_path / (slot["scenario"] + "-" + slot["mode"])
        directory.mkdir()
        save(directory / "attempt.json", {**slot, "registration_sha256": digest(tmp_path / "registration.json")})
        # Synthetic scorer inputs only, not provider evidence or reported performance.
        output = {"content": "answer"} if slot["mode"] == "direct_model" else {"result": {"message": "answer"}}
        save(directory / "report.json", {"scenario_id": slot["scenario"], "mode": slot["mode"],
             "output": output, "objective_pass": None if slot["mode"] == "direct_model" else True,
             "business_unchanged": True,
             "measurements": {"unauthorized_writes": {"count": 0, "complete": True}}})
    return tmp_path


def filled(batch):
    review = prepare(batch)
    for item in review["trials"]:
        if item["mode"] == "fixed_workflow":
            continue
        item["reviewer"] = {"kind": "codex", "name": "test reviewer"}
        pointer = "/output/content" if item["mode"] == "direct_model" else "/output/result/message"
        for criterion in item["criteria"].values():
            criterion.update(passed=True, evidence=[{"file": "report.json", "pointer": pointer,
                                                    "reason": "synthetic scorer fixture"}])
    return review


def test_pending_and_complete_scores_do_not_change_holdout(batch):
    pending = batch / "pending.json"
    save(pending, prepare(batch))
    assert [r["task_success"] for r in score_review(pending)["slots"]] == [True, None, None] * 2
    complete = batch / "complete.json"
    save(complete, filled(batch))
    result = score_review(complete)
    assert len(result["slots"]) == 6 and all(r["task_success"] for r in result["slots"])
    assert all(r["human_clarity"] is None for r in result["slots"])
    assert result["holdout_gate"] == "unchanged_failed"


def test_objective_failure_cannot_be_overturned_by_semantic_ratings(batch):
    path = next(batch.glob("*-agent_tools/report.json"))
    report = json.loads(path.read_text(encoding="utf-8"))
    report["objective_pass"] = False
    path.write_text(json.dumps(report), encoding="utf-8")
    review = batch / "review.json"
    save(review, filled(batch))
    scores = score_review(review)["slots"]
    failed = next(s for s in scores if s["scenario"] == report["scenario_id"] and s["mode"] == "agent_tools")
    assert failed["task_success"] is False


@pytest.mark.parametrize("mutation", ["report", "omit", "rubric", "clarity", "pointer"])
def test_tampering_and_nonhuman_clarity_are_rejected(batch, mutation):
    review = filled(batch)
    if mutation == "report":
        path = next(batch.glob("*-agent_tools/report.json"))
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    elif mutation == "omit":
        review["trials"].pop()
    elif mutation == "rubric":
        review["trials"][1]["rubric"]["prompt"] = "changed"
    elif mutation == "clarity":
        review["trials"][1]["human_clarity"] = 5
    else:
        review["trials"][1]["criteria"]["intent"]["evidence"][0]["pointer"] = "/absent"
    path = batch / "review.json"
    save(path, review)
    with pytest.raises(ValueError):
        score_review(path)


def test_unstarted_six_slots_remain_missing(tmp_path):
    save(tmp_path / "registration.json", registration(load_protocol(), Settings(_env_file=None)))
    path = tmp_path / "review.json"
    save(path, prepare(tmp_path))
    assert [r["task_success"] for r in score_review(path)["slots"]] == [None] * 6


def test_missing_final_answer_cannot_receive_semantic_rating(batch):
    path = next(batch.glob("*-agent_tools/report.json"))
    report = json.loads(path.read_text(encoding="utf-8"))
    report["output"] = {"result": {"message": ""}}
    path.write_text(json.dumps(report), encoding="utf-8")
    review = batch / "review.json"
    save(review, filled(batch))
    with pytest.raises(ValueError, match="language evidence"):
        score_review(review)
