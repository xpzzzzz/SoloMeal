import pytest
from scripts.cohort_metrics import distribution, outcomes, query_observations, summarize
from scripts.review_agent import main as review_main
from test_agent_cohort import read, seed, setup_plan, write


@pytest.fixture(autouse=True)
def private_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.cohort_agent.REPOSITORY", tmp_path / "repository")


def test_empty_cohort_keeps_all_modes_and_no_success(tmp_path):
    plan, hashed = setup_plan(tmp_path)
    result = summarize(plan, hashed)
    assert result["p8_gate"] == "incomplete" and result["holdout_gate"] == "not_run"
    for mode, metrics in result["modes"].items():
        assert metrics["scheduled_trials"] == 60
        assert metrics["task_success"]["rate"] is None
        assert metrics["latency_seconds"]["missing"] == 60
        assert metrics["usage"]["observed_total_tokens"] is None
        assert metrics["write_correctness"]["status"] == ("not_applicable" if mode == "direct_model" else "incomplete")
        assert metrics["required_query"]["value"] is None
        assert metrics["task_success"]["not_applicable"] == (18 if mode == "direct_model" else 0)


@pytest.mark.parametrize("version", ["evaluation-measurements-v2", "evaluation-measurements-v3"])
def test_required_query_counts_declared_trials_without_gating(version):
    def report(tools, declared=("recommend_meal",)):
        return {"measurements": {"version": version, "required_query": {
            "required": list(declared), "observed": sorted(tools),
            "satisfied": all(t in tools for t in declared) if declared else None,
            "answered_without_query": bool(declared) and not tools}}}
    older = {"measurements": {"version": "evaluation-measurements-v1"}}
    counts = query_observations([("A026", report({"recommend_meal"})), ("A027", report({"get_inventory"})),
                                 ("A024", report({"get_inventory"}, ())), ("A025", older)], "agent_tools")
    assert (counts["declared"], counts["satisfied"], counts["unsatisfied"]) == (2, 1, 1)
    assert counts["missing_required_query"] == 1 and counts["not_measured"] == 2
    assert "answered_without_query" not in counts
    assert counts["value"] is None and counts["threshold"] is None
    assert counts["status"] == "observation_only"
    baselines = query_observations([("A026", report({"recommend_meal"}))], "fixed_workflow")
    assert baselines["status"] == "not_applicable" and baselines["not_measured"] == 1


def test_failure_usage_and_latency_without_review(tmp_path):
    plan, hashed = setup_plan(tmp_path)
    directory = seed(plan)
    report = read(directory / "report.json")
    report.update(elapsed_seconds=31.2, invalid_calls=0)
    report["model_calls"][0]["usage"] = {"total_tokens": None}
    write(directory / "report.json", report)
    write(directory / "call-01-result.json", {"metadata": report["model_calls"][0]})
    metrics = summarize(plan, hashed)["modes"]["agent_tools"]
    assert metrics["task_success"]["failed"] == 1
    assert metrics["task_success"]["missing"] == 59
    assert metrics["latency_seconds"]["observed_value"] == 31.2
    assert metrics["latency_seconds"]["value"] is None
    assert metrics["invalid_calls"]["status"] == "incomplete"
    assert metrics["usage"]["missing_usage_calls"] == 1
    assert metrics["usage"]["cost"] is None


def test_reviewed_fixed_success_not_language_or_write_gate(tmp_path):
    plan, hashed = setup_plan(tmp_path)
    directory = seed(plan, mode="fixed_workflow", objective=True)
    review = tmp_path / "review.json"
    review_main(["init", "--trial", str(directory), "--output", str(review)])
    metrics = summarize(plan, hashed, review)["modes"]["fixed_workflow"]
    assert metrics["task_success"]["passed"] == 1
    assert metrics["task_success"]["confirmed_success_fraction"] == 1 / 60
    assert metrics["hard_constraints"]["missing"] == 60
    assert metrics["hard_constraints"]["status"] == "not_applicable"
    assert metrics["human_clarity"]["status"] == "not_applicable"
    assert metrics["write_correctness"]["value"] is None


@pytest.mark.parametrize("values,expected", [([1] * 19 + [121], 1), ([1] * 18 + [121] * 2, 121)])
def test_nearest_rank_p95_and_threshold(values, expected):
    result = distribution(values, 120, reduction="p95")
    assert result["value"] == expected
    assert result["status"] == ("passed" if expected <= 120 else "failed")


@pytest.mark.parametrize("bad", [None, True, -1, float("nan"), float("inf"), "3"])
def test_invalid_numbers_remain_missing(bad):
    result = distribution([2, bad], 120)
    assert result["missing"] == 1 and result["value"] is None
    assert result["status"] == "incomplete"


def test_no_best_of_or_unscored_denominator_removal():
    assert outcomes([True, False, None]) == {
        "passed": 1, "failed": 1, "missing": 1, "scheduled": 3,
        "rate": None, "confirmed_success_fraction": 1 / 3}


@pytest.mark.parametrize("mutation,expected", [
    (None, "passed"), ("threshold", "passed"), ("task_failures", "failed"), ("missing_review", "incomplete"),
    ("missing_report", "incomplete"), ("hard_failure", "failed"),
    ("clarity_missing", "incomplete"), ("clarity_low", "failed"),
    ("baseline_failure", "failed"),
])
def test_complete_holdout_gates_use_applicable_metrics(tmp_path, monkeypatch, mutation, expected):
    from scripts import cohort_metrics
    from scripts.cohort_agent import slots

    rows = slots(tmp_path / "synthetic", "holdout")
    for index, row in enumerate(rows):
        row.update(status="awaiting_review", evidence_sha256={"report.json": "synthetic"})
        fixed = row["mode"] == "fixed_workflow"
        row["review"] = {"task_success": True, "decision_success": True,
                         "constraint_pass": None if fixed else True,
                         "human_clarity": None if fixed else (3 if index % 2 else 5)}
    agent = [r for r in rows if r["mode"] == "agent_tools"]
    if mutation in ("task_failures", "threshold"):
        for row in agent[:9 if mutation == "threshold" else 10]:
            row["review"]["task_success"] = False
    elif mutation == "missing_review":
        agent[0]["review"] = {}
    elif mutation == "missing_report":
        agent[0].update(status="not_started", evidence_sha256={})
    elif mutation == "hard_failure":
        agent[0]["review"]["constraint_pass"] = False
    elif mutation == "clarity_missing":
        agent[0]["review"]["human_clarity"] = None
    elif mutation == "clarity_low":
        for row in agent:
            row["review"]["human_clarity"] = 3
    elif mutation == "baseline_failure":
        for row in [r for r in rows if r["mode"] == "fixed_workflow"][:10]:
            row["review"]["task_success"] = False
    report = {"elapsed_seconds": 1, "invalid_calls": 0, "measurements": {
        "version": "evaluation-measurements-v1", "arguments": {"valid": 1, "total": 1},
        "write_correctness": {"passed": True}, "unauthorized_writes": {"complete": True, "count": 0}}}
    original_read = cohort_metrics.read
    monkeypatch.setattr(cohort_metrics, "audit", lambda *args: {"split": "holdout", "trials": rows})
    monkeypatch.setattr(cohort_metrics, "digest", lambda path: "synthetic")
    monkeypatch.setattr(cohort_metrics, "read", lambda path:
                        report if path.name == "report.json" else original_read(path))
    result = summarize(tmp_path / "not-a-real-manifest", "synthetic")
    assert result["holdout_gate"] == expected
    assert result["p8_gate"] == "incomplete"
    assert result["modes"]["fixed_workflow"]["hard_constraints"]["status"] == "not_applicable"
    if mutation is None:
        assert result["modes"]["agent_tools"]["human_clarity"]["value"] == 4
        assert result["modes"]["agent_tools"]["human_clarity"]["reduction"] == "mean"


def test_semantic_constraint_failure_and_codex_not_human(tmp_path):
    plan, hashed = setup_plan(tmp_path)
    directory = seed(plan, objective=True)
    review = tmp_path / "review.json"
    review_main(["init", "--trial", str(directory), "--output", str(review)])
    data = read(review)
    item = data["trials"][0]
    item["reviewer"] = {"kind": "codex", "name": "test reviewer"}
    item["criteria"]["constraints"] = {"passed": False, "evidence": [{
        "file": "report.json", "pointer": "/objective_pass", "reason": "Synthetic test reference"}]}
    write(review, data)
    metrics = summarize(plan, hashed, review)["modes"]["agent_tools"]
    assert metrics["hard_constraints"]["status"] == "failed"
    assert metrics["task_success"]["failed"] == 1
    assert metrics["human_clarity"]["missing"] == 60


def test_cli_summary_creates_new_artifact_and_refuses_overwrite(tmp_path):
    import subprocess
    import sys
    import tempfile
    from pathlib import Path
    from uuid import uuid4

    from scripts.cohort_agent import digest, register

    plan, hashed = setup_plan(tmp_path)
    config = read(plan)["config"]
    plan = tmp_path / "cli-manifest.json"
    register(config, Path(tempfile.gettempdir()) / ("cohort-" + uuid4().hex), plan, "debug")
    hashed = digest(plan)
    output = tmp_path / "summary.json"
    script = Path(__file__).resolve().parents[1] / "scripts/cohort_agent.py"
    args = [sys.executable, str(script), "summarize", "--manifest", str(plan),
            "--manifest-sha256", hashed, "--output", str(output)]
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert read(output)["cohort"]["scheduled_trials"] == 180
    original = output.read_bytes()
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode != 0 and output.read_bytes() == original
