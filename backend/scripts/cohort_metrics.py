"""Conservative cohort summaries by frozen split; missing measurements never become passes."""

import math
from pathlib import Path

from scripts.cohort_agent import (
    CONFIRMATION_SCENARIOS,
    EVALUATION,
    audit,
    bind_review,
    digest,
    read,
)
from scripts.review_agent import DIRECT_EXECUTION

VERSION = "solomeal-cohort-metrics-v6"
# Every reported gate for a cohort; the frozen README additionally requires the engineering suite.
GATED = ("task_success", "hard_constraints", "invalid_calls", "human_clarity",
         "valid_tool_arguments", "write_correctness", "unauthorized_writes", "latency_seconds")


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def distribution(values, threshold, *, reduction="mean", minimum=False):
    known = [v for v in values if numeric(v)]
    value = None
    if known:
        if reduction == "p95":
            value = sorted(known)[math.ceil(len(known) * .95) - 1]
        elif reduction == "min":
            value = min(known)
        else:
            value = sum(known) / len(known)
    complete = bool(values) and len(known) == len(values)
    # Partial mean/percentile is descriptive, not a complete-cohort gate.
    state = "incomplete"
    if complete:
        state = "passed" if (value >= threshold if minimum else value <= threshold) else "failed"
    return {"value": value if complete else None, "observed_value": value,
            "observed": len(known), "scheduled": len(values), "missing": len(values) - len(known),
            "threshold": threshold, "status": state, "reduction": reduction}


def outcomes(values):
    passed = sum(v is True for v in values)
    failed = sum(v is False for v in values)
    missing = len(values) - passed - failed
    return {"passed": passed, "failed": failed, "missing": missing, "scheduled": len(values),
            "rate": passed / len(values) if values and not missing else None,
            "confirmed_success_fraction": passed / len(values) if values else None}


def overall(statuses):
    values = [status for status in statuses if status != "not_applicable"]
    return ("failed" if "failed" in values else "incomplete" if "incomplete" in values
            else "passed" if values else "incomplete")


def measured_gates(reports, mode, protocol, write_scenarios):
    arguments, writes, unauthorized = [], [], []
    argument_missing = 0
    for scenario, report in reports:
        measure = report.get("measurements", {})
        # Query observation revisions do not change any gated measurement.
        if measure.get("version") not in ("evaluation-measurements-v1", "evaluation-measurements-v2",
                                           "evaluation-measurements-v3"):
            measure = {}
        args = measure.get("arguments", {})
        valid, total = args.get("valid"), args.get("total")
        if type(valid) is int and type(total) is int and 0 <= valid <= total:
            arguments.append((valid, total))
        else:
            argument_missing += 1
        if scenario in write_scenarios:
            value = measure.get("write_correctness", {}).get("passed")
            writes.append(value if type(value) is bool else None)
        observed = measure.get("unauthorized_writes", {})
        count = observed.get("count")
        unauthorized.append(count if observed.get("complete") is True and type(count) is int and count >= 0 else None)
    numerator = sum(v for v, t in arguments)
    denominator = sum(t for v, t in arguments)
    ratio = numerator / denominator if denominator else None
    arg_status = "incomplete" if argument_missing else "not_applicable" if not denominator else (
        "passed" if ratio >= protocol["valid_tool_arguments_min"] else "failed")
    write = outcomes(writes)
    write.update(value=write["rate"], threshold=protocol["write_correctness_min"],
                 status="not_applicable" if not writes else "failed" if write["failed"] else
                 "incomplete" if write["missing"] else "passed")
    known = [v for v in unauthorized if v is not None]
    observed_count = sum(known)
    result = {
        "valid_tool_arguments": {"value": ratio if not argument_missing else None,
            "observed_ratio": ratio, "valid": numerator, "total": denominator,
            "missing_trials": argument_missing, "status": arg_status,
            "threshold": protocol["valid_tool_arguments_min"]},
        "write_correctness": write,
        "unauthorized_writes": {"value": observed_count if len(known) == len(reports) else None,
            "observed_count": observed_count, "missing_trials": len(reports) - len(known),
            "threshold": protocol["unauthorized_writes_max"],
            "status": "failed" if observed_count > protocol["unauthorized_writes_max"] else
            "incomplete" if len(known) != len(reports) else "passed",
            "unit": "business_DML_statements_at_commit_boundary"},
    }
    if mode == "direct_model":
        for key in ("valid_tool_arguments", "write_correctness"):
            result[key].update(value=None, status="not_applicable")
    return result


def query_observations(reports, mode):
    """Observation only: a missing query is a different gap from a query whose answer was wrong."""
    declared = satisfied = 0
    if mode == "agent_tools":
        for _, report in reports:
            measure = report.get("measurements", {})
            observed = (measure.get("required_query", {})
                        if measure.get("version") in ("evaluation-measurements-v2",
                                                      "evaluation-measurements-v3") else {})
            if not observed.get("required"):
                continue
            declared += 1
            satisfied += observed.get("satisfied") is True
    return {"status": "observation_only" if mode == "agent_tools" else "not_applicable",
            "value": None, "threshold": None, "declared": declared, "satisfied": satisfied,
            "unsatisfied": declared - satisfied, "missing_required_query": declared - satisfied,
            "not_measured": len(reports) - declared,
            "scope": "declared_by_harness_only; does not measure whether an answer was given; undeclared trials are not measured"}


def summarize(manifest, expected_sha256, review_path=None):
    cohort = (bind_review(manifest, expected_sha256, review_path) if review_path
              else audit(manifest, expected_sha256))
    protocol = read(EVALUATION / "protocol-v1.json")["agent"]
    split = cohort["split"]
    write_scenarios = CONFIRMATION_SCENARIOS[split]
    modes = {}
    for mode in protocol["modes"]:
        rows = [r for r in cohort["trials"] if r["mode"] == mode]
        tasks, decisions, constraints, latency, invalid, clarity = [], [], [], [], [], []
        tokens, requests, missing_usage, missing_reports = [], 0, 0, 0
        not_applicable = 0
        reports = []
        for row in rows:
            valid = row["status"] not in ("not_started", "invalid_evidence")
            score = row.get("review", {}) if valid else {}
            report = {}
            path = Path(row["directory"]) / "report.json"
            if valid and "report.json" in row["evidence_sha256"]:
                if digest(path) != row["evidence_sha256"]["report.json"]:
                    raise ValueError("Report changed during aggregation")
                report = read(path)
            if not report:
                missing_reports += 1
            reports.append((row["scenario"], report))
            applicable = not (mode == "direct_model" and row["scenario"] in DIRECT_EXECUTION)
            # Transport/objective failures count even without semantic review.
            failure = row["status"] == "failed" or (valid and not report)
            success = False if failure else score.get("task_success")
            if applicable:
                tasks.append(success)
            else:
                not_applicable += 1
            decisions.append(False if failure else score.get("decision_success"))
            constraints.append(score.get("constraint_pass"))
            latency.append(report.get("elapsed_seconds"))
            invalid.append(report.get("invalid_calls"))
            clarity.append(score.get("human_clarity"))
            # Read attempt/result pairs, including interrupted trials without reports.
            if valid:
                for name in row["evidence_sha256"]:
                    if not name.startswith("call-") or not name.endswith("-result.json"):
                        continue
                    call = Path(row["directory"]) / name
                    if digest(call) != row["evidence_sha256"][name]:
                        raise ValueError("Call changed during aggregation")
                    meta = read(call)["metadata"]
                    requests += int(meta.get("request_sent") is True)
                    total = meta.get("usage", {}).get("total_tokens")
                    if type(total) is int and total >= 0:
                        tokens.append(total)
                    else:
                        missing_usage += 1
        hard = outcomes(constraints)
        hard.update(threshold=protocol["hard_constraint_satisfaction_min"],
                    status="failed" if hard["failed"] else
                    "incomplete" if hard["missing"] else "passed",
                    source="review_constraints_only; fixed objective is not a substitute")
        if mode == "fixed_workflow":
            hard.update(status="not_applicable", rate=None,
                        source="no_language_review; objective_constraints_checked_in_task_success")
        mean_latency = distribution(latency, protocol["task_p95_seconds_max"])
        mean_latency.update(status="report_only", threshold=None)
        task = outcomes(tasks)
        # A holdout rate is only reportable over the full denominator; missing never becomes a pass.
        task["status"] = ("debug_only" if split == "debug" else
                          "incomplete" if task["rate"] is None else
                          "passed" if task["rate"] >= protocol["holdout_task_success_min"] else "failed")
        modes[mode] = {
            "scheduled_trials": len(rows), "task_success": {**task,
                "not_applicable": not_applicable,
                "holdout_threshold": protocol["holdout_task_success_min"]},
            "decision_success": outcomes(decisions), "hard_constraints": hard,
            "latency_seconds": distribution(latency, protocol["task_p95_seconds_max"], reduction="p95"),
            "latency_mean_seconds": mean_latency,
            "invalid_calls": distribution(invalid, protocol["invalid_calls_mean_max"]),
            "human_clarity": ({"status": "not_applicable", "value": None} if mode == "fixed_workflow"
                else distribution(clarity, protocol["clarity_human_score_min"], minimum=True)),
            **measured_gates(reports, mode, protocol, write_scenarios),
            "required_query": query_observations(reports, mode),
            "usage": {"observed_requests": requests, "observed_total_tokens": sum(tokens) if tokens else None,
                      "known_usage_calls": len(tokens), "missing_usage_calls": missing_usage,
                      "missing_reports": missing_reports,
                      "total_tokens": sum(tokens) if not missing_reports and not missing_usage else None,
                      "cost": None,
                      "scope": "observed_only; incomplete trials and missing usage remain unknown"},
        }
    gates = {mode: {key: result[key]["status"] for key in GATED
                    if key != "task_success" or split == "holdout"}
             for mode, result in modes.items()}
    statuses = [status for result in gates.values() for status in result.values()]
    return {"version": VERSION, "manifest_sha256": expected_sha256,
            "aggregator_sha256": digest(Path(__file__)), "protocol": protocol,
            "split": split, "modes": modes, "gates": gates, "cohort": cohort,
            "p8_gate": "incomplete",
            "holdout_gate": overall(statuses) if split == "holdout" else "not_run",
            "scope": ("holdout_gates_over_full_denominator; synthetic holdout without independent "
                      "human review; P8 also requires engineering and deployment evidence"
                      if split == "holdout" else "debug_metrics_not_formal_acceptance")}
