import pytest
from scripts.cohort_agent import CONFIRMATION_SCENARIOS, EVALUATION, read, slot_confirmation
from scripts.cohort_metrics import measured_gates
from scripts.evaluate_agent import trial
from scripts.evaluation_measurements import WriteObserver, measurements
from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from test_agent_evaluation import case


def test_observer_counts_commit_not_rollback_and_excludes_driver():
    engine = create_engine("sqlite://")
    table = Table("inventory_batches", MetaData(), Column("id", Integer, primary_key=True))
    table.metadata.create_all(engine)
    with WriteObserver(engine) as observer:
        with engine.begin() as conn:
            conn.execute(table.insert().values(id=1))  # Setup is outside measurement window.
        observer.active = True
        with engine.connect() as conn:
            conn.execute(table.insert().values(id=2))
            conn.rollback()
        with observer.driver_write(True), engine.begin() as conn:
            conn.execute(table.insert().values(id=3))
        with engine.begin() as conn:
            conn.execute(table.insert().values(id=4))
        assert observer.result()["count"] == 1
        assert observer.result()["attempted_statements"] == 2
        assert observer.result()["complete"] is True
    with engine.begin() as conn:
        conn.execute(table.insert().values(id=5))
    assert observer.result()["count"] == 1  # Listener removed.
    engine.dispose()


def test_raw_dml_cannot_silently_pass_observer():
    engine = create_engine("sqlite://")
    with WriteObserver(engine) as observer, engine.begin() as conn:
        observer.active = True
        conn.exec_driver_sql("CREATE TABLE example (id INTEGER)")
        conn.exec_driver_sql("INSERT INTO example VALUES (1)")
    assert not observer.result()["complete"]
    engine.dispose()


def test_committed_write_then_restore_is_not_hidden_by_equal_snapshot():
    engine = create_engine("sqlite://")
    table = Table("inventory_batches", MetaData(), Column("id", Integer, primary_key=True))
    table.metadata.create_all(engine)
    with WriteObserver(engine) as observer:
        observer.active = True
        with engine.begin() as conn:
            conn.execute(table.insert().values(id=1))
            conn.execute(table.delete())
        assert observer.result()["count"] == 2
    engine.dispose()


@pytest.mark.parametrize("split,scenario,mode,expected", [
    ("debug", "A010", "agent_tools", "approve"), ("debug", "A011", "fixed_workflow", "approve"),
    ("debug", "A012", "direct_model", "none"), ("debug", "A019", "agent_tools", "none"),
    ("debug", "A030", "agent_tools", "none"),
    ("holdout", "A030", "agent_tools", "approve"), ("holdout", "A033", "fixed_workflow", "approve"),
    ("holdout", "A031", "direct_model", "none"), ("holdout", "A036", "agent_tools", "none"),
    ("holdout", "A010", "agent_tools", "none")])
def test_registered_approval_policy_only_targets_supported_execution(split, scenario, mode, expected):
    plan = {"split": split, "config": {"attempt": {"confirmation_extension": "approve"}}}
    assert slot_confirmation(plan, {"scenario": scenario, "mode": mode}) == expected


def test_required_query_separates_no_query_from_a_wrong_answer():
    observer = WriteObserver(None)

    def events(code):
        return {"output": {"events": [{"tool": "recommend_meal",
                                       "result": {"error": {"code": code}} if code
                                       else {"candidates": []}}]}}

    met = measurements({**events(None), "required_query": ["recommend_meal"]}, observer)
    assert met["version"] == "evaluation-measurements-v3"
    assert met["required_query"]["satisfied"] is True
    assert met["required_query"]["observed"] == ["recommend_meal"]
    assert met["required_query"]["missing_required_query"] is False
    silent = measurements({**events("TOOL_TIMEOUT"), "required_query": ["recommend_meal"]}, observer)
    assert silent["required_query"]["observed"] == []
    assert silent["required_query"]["satisfied"] is False
    assert silent["required_query"]["missing_required_query"] is True
    assert silent["required_query"]["missing"] == ["recommend_meal"]
    undeclared = measurements(events(None), observer)
    assert undeclared["required_query"] == {
        "required": [], "observed": ["recommend_meal"], "satisfied": None,
        "missing": [], "missing_required_query": None, "scope": undeclared["required_query"]["scope"]}


@pytest.mark.parametrize("status", ["completed", "failed", "ready"])
@pytest.mark.parametrize("result", [{"items": []}, None, {"error": {"code": "TOOL_TIMEOUT"}}])
def test_unrelated_query_cannot_satisfy_requirement_or_imply_an_answer(status, result):
    report = {"required_query": ["recommend_meal"], "output": {
        "status": status, "events": [{"tool": "get_inventory", "result": result}]}}
    # A persisted null result is not evidence of successful completion.
    report["output"]["events"].append({"tool": "recommend_meal", "result": None})
    observed = measurements(report, WriteObserver(None))["required_query"]
    assert observed["satisfied"] is False
    assert observed["missing"] == ["recommend_meal"]
    assert observed["missing_required_query"] is True
    assert "answered_without_query" not in observed


def test_all_required_queries_must_succeed():
    report = {"required_query": ["get_inventory", "recommend_meal"], "output": {
        "events": [{"tool": "get_inventory", "result": {"items": []}}]}}
    observed = measurements(report, WriteObserver(None))["required_query"]
    assert observed["observed"] == ["get_inventory"]
    assert observed["missing"] == ["recommend_meal"]
    assert observed["missing_required_query"] is True


def test_parameter_errors_are_separate_from_business_and_timeout_errors():
    observer = WriteObserver(None)
    report = {"output": {"events": [{"result": {"error": {"code": code}}}
              for code in ["INVALID_TOOL_ARGUMENTS", "UNKNOWN_TOOL", "INSUFFICIENT_STOCK", "TOOL_TIMEOUT"]]}}
    result = measurements(report, observer)
    assert result["arguments"]["valid"] == 2
    assert result["arguments"]["total"] == 4
    assert result["write_correctness"]["passed"] is None


@pytest.mark.parametrize("scenario", ["A010", "A011", "A012", "A030", "A031", "A033"])
def test_approved_write_has_quantity_and_replay_measurement(client, scenario):
    result = trial(client, case(scenario), "fixed_workflow", confirmation="approve")
    measured = result["measurements"]
    assert measured["write_correctness"]["passed"] is True
    assert measured["arguments"]["total"] > 0
    assert measured["unauthorized_writes"]["count"] == 0
    assert measured["unauthorized_writes"]["complete"]
    assert not hasattr(client.app.state, "evaluation_observer")


def test_preview_does_not_claim_write_correctness(client):
    result = trial(client, case("A010"), "fixed_workflow")
    assert result["measurements"]["write_correctness"]["passed"] is None


def test_elapsed_includes_driver_confirmation(client, monkeypatch):
    from types import SimpleNamespace

    from scripts import evaluate_agent

    clock = [0]
    original = evaluate_agent.confirm_extension

    def delayed_confirmation(*args):
        result = original(*args)
        clock[0] = 50
        return result

    monkeypatch.setattr(evaluate_agent, "time", SimpleNamespace(perf_counter=lambda: clock[0]))
    monkeypatch.setattr(evaluate_agent, "confirm_extension", delayed_confirmation)
    result = trial(client, case("A010"), "fixed_workflow", confirmation="approve")
    assert result["elapsed_seconds"] == 50
    assert result["confirmation_passed"]


def test_measurement_gates_keep_missing_denominators_and_observed_violation():
    protocol = read(EVALUATION / "protocol-v1.json")["agent"]
    report = {"measurements": {"version": "evaluation-measurements-v1",
              "arguments": {"valid": 9, "total": 10},
              "write_correctness": {"passed": False},
              "unauthorized_writes": {"complete": True, "count": 1}}}
    gates = measured_gates([("A010", report), ("A011", {})], "agent_tools", protocol,
                           CONFIRMATION_SCENARIOS["debug"])
    assert gates["valid_tool_arguments"]["value"] is None
    assert gates["valid_tool_arguments"]["observed_ratio"] == .9
    assert gates["write_correctness"]["status"] == "failed"
    assert gates["write_correctness"]["missing"] == 1
    assert gates["unauthorized_writes"]["status"] == "failed"
    assert gates["unauthorized_writes"]["value"] is None
