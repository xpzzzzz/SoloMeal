import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from app.services.agent_model import fingerprint
from scripts.cohort_agent import (
    ATTEMPT_KEYS,
    EVALUATION,
    MODEL_KEYS,
    audit,
    bind_review,
    digest,
    preflight,
    read,
    register,
    slot_confirmation,
)
from scripts.review_agent import main as review_main


@pytest.fixture(autouse=True)
def isolated_repository_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.cohort_agent.REPOSITORY", tmp_path / "repository")


def setup_plan(tmp_path, split="debug"):
    config = {"attempt": {key: "test" for key in ATTEMPT_KEYS},
              "model": {key: "test" for key in MODEL_KEYS}}
    config["attempt"].update(max_completion_tokens=3000, model_timeout_seconds=30,
                             tool_protocol="json", confirmation_extension="none",
                             direct_system_sha256=fingerprint("test"))
    plan = tmp_path / "manifest.json"
    register(config, tmp_path / "private-runs", plan, split)
    return plan, digest(plan)


def seed(plan, mode="agent_tools", objective=False):
    data = read(plan)
    slot = next(s for s in data["trials"] if s["mode"] == mode)
    directory = Path(slot["directory"])
    directory.mkdir(parents=True)
    attempt = {**data["config"]["attempt"], **data["data_sha256"],
               "scenario": slot["scenario"], "mode": mode, "repetitions": 1,
               "cohort": {"manifest_sha256": digest(plan), "repetition": slot["repetition"]},
               "started_at": datetime.now(timezone.utc).isoformat()}
    write(directory / "attempt.json", attempt)
    calls = []
    if mode != "fixed_workflow":
        meta = {**data["config"]["model"], "max_completion_tokens": 3000,
                "timeout_seconds": 30, "request_sent": True,
                "tool_protocol": "json" if mode == "agent_tools" else "native"}
        calls.append(meta)
        write(directory / "call-01-attempt.json", {})
        if mode == "direct_model":
            payload = {"messages": [{"role": "system", "content": "test"}], "tools": []}
            hashes = {"messages_sha256": fingerprint(payload["messages"]),
                      "tools_sha256": fingerprint([])}
            meta.update(**hashes, wire_messages_sha256=hashes["messages_sha256"])
            write(directory / "call-01-attempt.json", hashes)
            write(directory / "call-01-input.json", payload)
        write(directory / "call-01-result.json", {"metadata": meta})
    write(directory / "report.json", {"scenario_id": slot["scenario"], "mode": mode,
          "model_calls": calls, "actual_requests": len(calls),
          "objective_pass": objective, "business_unchanged": True})
    return directory


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_all_unstarted_slots_remain_in_denominator(tmp_path):
    plan, hashed = setup_plan(tmp_path)
    result = audit(plan, hashed)
    assert result["scheduled_trials"] == result["counts"]["not_started"] == 180
    assert result["success_rate"] is None and result["p8_gate"] == "incomplete"
    assert not Path(read(plan)["trial_root"]).exists()
    with pytest.raises(FileExistsError):
        register(read(plan)["config"], tmp_path / "another", plan, "debug")


@pytest.mark.parametrize("mode", ["agent_tools", "direct_model", "fixed_workflow"])
def test_failures_are_retained_without_semantic_success(tmp_path, mode):
    plan, hashed = setup_plan(tmp_path)
    seed(plan, mode)
    result = audit(plan, hashed)
    assert result["counts"]["failed"] == 1
    assert result["counts"]["not_started"] == 179
    assert result["counts"]["invalid_evidence"] == 0


@pytest.mark.parametrize("mutation", ["config", "missing_result", "orphan", "old_trial", "report", "binding"])
def test_bad_evidence_cannot_count_as_completed(tmp_path, mutation):
    plan, hashed = setup_plan(tmp_path)
    directory = seed(plan, objective=True)
    if mutation == "missing_result":
        (directory / "call-01-result.json").unlink()
    elif mutation == "orphan":
        write(directory / "call-02-result.json", {})
    elif mutation == "report":
        report = read(directory / "report.json")
        report["actual_requests"] = 0
        write(directory / "report.json", report)
    else:
        attempt = read(directory / "attempt.json")
        if mutation == "binding":
            attempt.pop("cohort")
        else:
            attempt["source_sha256" if mutation == "config" else "started_at"] = (
                "different" if mutation == "config" else "2000-01-01T00:00:00+00:00")
        write(directory / "attempt.json", attempt)
    result = audit(plan, hashed)
    assert result["counts"]["invalid_evidence"] == 1
    assert result["counts"]["not_started"] == 179


def test_manifest_tampering_and_existing_root_rejected(tmp_path):
    plan, hashed = setup_plan(tmp_path)
    data = read(plan)
    data["trials"].pop()
    write(plan, data)
    with pytest.raises(ValueError, match="hash"):
        audit(plan, hashed)
    with pytest.raises(ValueError, match="Every planned"):
        audit(plan, digest(plan))
    existing = tmp_path / "exists"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        register(data["config"], existing, tmp_path / "second.json", "debug")


def test_unfinished_and_unexpected_entries_are_visible(tmp_path):
    plan, hashed = setup_plan(tmp_path)
    directory = seed(plan, objective=True)
    (directory / "report.json").unlink()
    (directory.parent / "unregistered-run").mkdir()
    result = audit(plan, hashed)
    assert result["counts"]["incomplete"] == 1
    assert result["unexpected_entries"] == ["unregistered-run"]


def test_model_config_mismatch_and_unreviewed_success(tmp_path):
    plan, hashed = setup_plan(tmp_path)
    directory = seed(plan, objective=True)
    assert audit(plan, hashed)["counts"]["awaiting_review"] == 1
    result = read(directory / "call-01-result.json")
    result["metadata"]["max_completion_tokens"] = 1500
    write(directory / "call-01-result.json", result)
    row = next(r for r in audit(plan, hashed)["trials"] if r["directory"] == str(directory))
    assert row["status"] == "invalid_evidence"
    assert "model:max_completion_tokens" in row["configuration_errors"]


@pytest.mark.parametrize("mutation,error", [
    ("missing", "missing_direct_input"), ("prompt", "direct_system_prompt"),
    ("tools", "direct_tools_present"), ("hash", "direct_input:messages_sha256"),
    ("wire", "direct_wire_messages"),
])
def test_direct_input_audit_rejects_unbound_evidence(tmp_path, mutation, error):
    plan, hashed = setup_plan(tmp_path)
    directory = seed(plan, "direct_model")
    path = directory / "call-01-input.json"
    payload = read(path)
    if mutation == "missing":
        path.unlink()
    elif mutation in ("prompt", "tools"):
        if mutation == "prompt":
            payload["messages"][0]["content"] = "old tool prompt"
        else:
            payload["tools"] = [{"type": "function"}]
        write(path, payload)
    else:
        path = directory / "call-01-result.json"
        result = read(path)
        result["metadata"]["wire_messages_sha256" if mutation == "wire"
                           else "messages_sha256"] = "wrong"
        write(path, result)
    row = next(r for r in audit(plan, hashed)["trials"] if r["directory"] == str(directory))
    assert row["status"] == "invalid_evidence"
    assert error in row["configuration_errors"]


def test_legacy_v3_remains_readable_without_fabricated_direct_inputs(tmp_path):
    plan, _ = setup_plan(tmp_path)
    data = read(plan)
    data["version"] = "solomeal-cohort-v3"
    del data["split"]
    for key in ("direct_prompt_version", "direct_system_sha256"):
        del data["config"]["attempt"][key]
    write(plan, data)
    directory = seed(plan, "direct_model")
    (directory / "call-01-input.json").unlink()
    result = audit(plan, digest(plan))
    assert result["split"] == "debug" and result["counts"]["failed"] == 1


def test_registration_rejects_repo_root_and_invalid_configuration(tmp_path):
    plan, _ = setup_plan(tmp_path)
    config = read(plan)["config"]
    with pytest.raises(ValueError, match="outside repository"):
        register(config, tmp_path / "repository" / "runs", tmp_path / "new.json", "debug")
    config["attempt"]["max_completion_tokens"] = True
    with pytest.raises(ValueError, match="Unsupported budget"):
        register(config, tmp_path / "runs", tmp_path / "new.json", "debug")
    with pytest.raises(ValueError, match="Unsupported cohort split"):
        register(read(plan)["config"], tmp_path / "runs", tmp_path / "new.json", "public")


def test_each_split_registers_its_own_frozen_scenarios(tmp_path):
    cases = read(EVALUATION / "scenarios-v1.json")["scenarios"]
    scenarios = {}
    for split in ("debug", "holdout"):
        (tmp_path / split).mkdir()
        plan, _ = setup_plan(tmp_path / split, split)
        data = read(plan)
        expected = sorted(c["id"] for c in cases if c["track"] == "agent" and c["split"] == split)
        assert data["split"] == split
        assert sorted({row["scenario"] for row in data["trials"]}) == expected
        # Three frozen modes and three repetitions per scenario stay in the registered order.
        assert len(data["trials"]) == len(expected) * 9
        scenarios[split] = {row["scenario"] for row in data["trials"]}
    # The cohorts are disjoint slots, so a holdout batch cannot join a debug trial root.
    assert not scenarios["debug"] & scenarios["holdout"]


@pytest.mark.parametrize("scenario,mode,expected", [
    ("A030", "agent_tools", "approve"), ("A031", "fixed_workflow", "approve"),
    ("A033", "agent_tools", "approve"), ("A030", "direct_model", "none"),
    ("A036", "agent_tools", "none"), ("A039", "agent_tools", "none"),
    ("A010", "agent_tools", "none")])
def test_registered_approval_follows_the_cohort_split(scenario, mode, expected):
    plan = {"split": "holdout", "config": {"attempt": {"confirmation_extension": "approve"}}}
    assert slot_confirmation(plan, {"scenario": scenario, "mode": mode}) == expected


def test_audit_reports_the_split_bound_in_the_manifest(tmp_path):
    plan, hashed = setup_plan(tmp_path, "holdout")
    result = audit(plan, hashed)
    assert result["split"] == "holdout" and result["scheduled_trials"] == 180
    assert {row["scenario"] for row in result["trials"]} >= {"A021", "A040"}


@pytest.mark.parametrize("mutation", [None, "source_sha256", "direct_prompt_version",
                                      "direct_system_sha256", "mode", "model", "output", "exists"])
def test_preflight_rejects_before_creating_output(tmp_path, mutation):
    plan, hashed = setup_plan(tmp_path)
    data = read(plan)
    slot = data["trials"][0]
    directory = Path(slot["directory"])
    attempt = {**data["config"]["attempt"], **data["data_sha256"],
               "scenario": slot["scenario"], "mode": slot["mode"], "repetitions": 1,
               "started_at": datetime.now(timezone.utc).isoformat()}
    model = data["config"]["model"].copy()
    if mutation in ("source_sha256", "direct_prompt_version", "direct_system_sha256", "mode"):
        attempt[mutation] = "wrong"
    elif mutation == "model":
        model["model"] = "wrong"
    elif mutation == "output":
        directory = tmp_path / "unregistered"
    elif mutation == "exists":
        directory.mkdir(parents=True)
    if mutation:
        with pytest.raises((ValueError, FileExistsError)):
            preflight(plan, hashed, directory, attempt, model)
    else:
        assert preflight(plan, hashed, directory, attempt, model) == {
            "manifest_sha256": hashed, "repetition": 1}
    assert directory.exists() is (mutation == "exists")


def test_cohort_review_keeps_unstarted_and_failed_slots(tmp_path):
    plan, hashed = setup_plan(tmp_path)
    directory = seed(plan)
    review = tmp_path / "review.json"
    review_main(["init", "--trial", str(directory), "--output", str(review)])
    result = bind_review(plan, hashed, review)
    assert result["scheduled_trials"] == 180 and result["reviewed_trials"] == 1
    assert result["counts"]["not_started"] == 179
    row = next(r for r in result["trials"] if "review" in r)
    assert row["review"]["task_success"] is False
    assert result["success_rate"] is None and result["p8_gate"] == "incomplete"
    attempt = read(directory / "attempt.json")
    attempt["source_sha256"] = "tampered"
    write(directory / "attempt.json", attempt)
    with pytest.raises(ValueError):
        bind_review(plan, hashed, review)


@pytest.mark.parametrize("flag,expected", [(None, "not_sent"), ("--no-enable-thinking", "false"),
                                          ("--enable-thinking", "true")])
def test_executor_checks_cohort_before_side_effects(tmp_path, monkeypatch, flag, expected):
    from scripts import evaluate_agent

    output = tmp_path / "never-created"
    checked = []

    def reject(*args):
        checked.append(args)
        assert not output.exists()
        assert args[3]["enable_thinking"] == expected
        assert args[4]["enable_thinking"] == expected
        raise ValueError("preflight rejected")

    def forbidden(*args):
        pytest.fail("Database must not start after rejected preflight")

    monkeypatch.setattr(evaluate_agent, "preflight", reject)
    monkeypatch.setattr(evaluate_agent, "isolated_client", forbidden)
    with pytest.raises(ValueError, match="preflight rejected"):
        evaluate_agent.main(["--output", str(output), "--cohort", str(tmp_path / "manifest"),
                             "--cohort-sha256", "expected", *([flag] if flag else [])])
    assert len(checked) == 1 and not output.exists()


def test_cohort_review_rejects_other_cohort(tmp_path):
    plan, hashed = setup_plan(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    other_plan, _ = setup_plan(other)
    directory = seed(other_plan)
    review = tmp_path / "review.json"
    review_main(["init", "--trial", str(directory), "--output", str(review)])
    with pytest.raises(ValueError, match="outside this cohort"):
        bind_review(plan, hashed, review)
