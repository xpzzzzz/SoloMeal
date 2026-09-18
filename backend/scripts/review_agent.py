"""Offline, evidence-bound review of diagnostic trials; never calls a model or database."""

import argparse
import hashlib
import json
from pathlib import Path

EVALUATION = Path(__file__).resolve().parents[2] / "evaluation"
VERSION = "solomeal-review-v1"
MODES = {"fixed_workflow", "direct_model", "agent_tools"}
# Snapshot-only scenarios across both splits: a text answer cannot execute or observe recovery.
DIRECT_EXECUTION = {"A010", "A011", "A012", "A016", "A019", "A020",
                    "A030", "A031", "A033", "A036", "A039", "A040"}
CRITERIA = {
    "intent": "正确回应场景请求；追问仅限缺失的必要信息；多轮保留未修改条件。",
    "constraints": "满足有效oracle及份数、时间、厨具、忌口、预算；未知价格不保证预算。",
    "faithfulness": "数量/单位/状态与证据一致；不虚构操作、时间、菜谱或完成写入。",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def evidence(directory):
    paths = [directory / "attempt.json", *sorted(directory.glob("call-*.json"))]
    if (directory / "report.json").exists():
        paths.append(directory / "report.json")
    return {p.name: digest(p) for p in paths}


def rubric(scenario):
    case = next((c for c in read(EVALUATION / "scenarios-v1.json")["scenarios"]
                 if c["id"] == scenario and c["track"] == "agent"), None)
    if case is None:
        raise ValueError("Review requires a frozen agent scenario")
    result = {k: case[k] for k in ("id", "prompt", "oracle", "fixture")}
    for name in ("amendments-v1.1.json", "amendments-v1.2.json"):
        for amendment in read(EVALUATION / name)["amendments"]:
            if amendment["scenario_id"] == scenario:
                result.update({k: amendment[k] for k in ("oracle", "fixture") if k in amendment})
    return result


def entry(directory):
    directory = directory.resolve()
    attempt = read(directory / "attempt.json")
    scenario, mode = attempt["scenario"], attempt["mode"]
    if mode not in MODES:
        raise ValueError("Unsupported mode")
    report = read(directory / "report.json") if (directory / "report.json").exists() else None
    if report and (report["scenario_id"] != scenario or report["mode"] != mode):
        raise ValueError("Attempt/report identity mismatch")
    return {"directory": str(directory), "evidence_sha256": evidence(directory),
            "scenario": scenario, "mode": mode, "rubric": rubric(scenario),
            "reviewer": {"kind": None, "name": None},
            "criteria": {k: {"passed": None, "evidence": []} for k in CRITERIA},
            "human_clarity": None, "clarity_evidence": []}


def references(items, directory, hashes):
    if not isinstance(items, list) or not items:
        raise ValueError("A rating requires evidence references")
    for item in items:
        # JSON pointers reference values without copying private response text into reports.
        name, pointer = item["file"], item["pointer"]
        if name not in hashes or not isinstance(pointer, str) or not pointer.startswith("/"):
            raise ValueError("Invalid evidence reference")
        value = read(directory / name)
        try:
            for part in pointer[1:].split("/"):
                key = part.replace("~1", "/").replace("~0", "~")
                value = value[int(key)] if isinstance(value, list) else value[key]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise ValueError("Evidence pointer does not resolve") from exc
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError("Evidence reference requires a reason")


def score(item):
    directory = Path(item["directory"])
    fresh = entry(directory)
    for field in ("evidence_sha256", "scenario", "mode", "rubric"):
        if item[field] != fresh[field]:
            raise ValueError(f"Evidence or rubric changed: {field}")
    report = read(directory / "report.json") if "report.json" in fresh["evidence_sha256"] else {}
    criteria = item["criteria"]
    if set(criteria) != set(CRITERIA):
        raise ValueError("All review criteria must be retained")
    fixed = item["mode"] == "fixed_workflow"
    reviewer = item["reviewer"]
    ratings = [c["passed"] for c in criteria.values()]
    clarity = item["human_clarity"]
    if any(v is not None for v in ratings) or clarity is not None:
        if reviewer["kind"] not in ("human", "codex", "model") or not reviewer["name"]:
            raise ValueError("Identify the actual reviewer and kind")
    for criterion in criteria.values():
        value = criterion["passed"]
        if value is not None:
            if type(value) is not bool or fixed:
                raise ValueError("Semantic ratings are booleans; fixed intent is not language evaluation")
            references(criterion["evidence"], directory, fresh["evidence_sha256"])
    if clarity is not None:
        if fixed or reviewer["kind"] != "human" or type(clarity) is not int or not 1 <= clarity <= 5:
            raise ValueError("Clarity requires a human reviewer and integer 1..5")
        references(item["clarity_evidence"], directory, fresh["evidence_sha256"])
    semantic = False if False in ratings else True if all(v is True for v in ratings) else None
    objective = report.get("objective_pass")
    if objective is not None and type(objective) is not bool:
        raise ValueError("Objective result must be boolean or null")
    failed = (not report or objective is False or report.get("business_unchanged") is False
              or report.get("confirmation_passed") is False
              or any(report.get(k) and report[k].get("passed") is False
                     for k in ("confirmation_extension", "stale_approval")))
    applicable = not (item["mode"] == "direct_model" and item["scenario"] in DIRECT_EXECUTION)
    success = None
    if applicable:
        if failed or semantic is False:
            success = False
        elif fixed:
            success = True if objective is True else None
        elif item["mode"] == "direct_model" or objective is True:
            success = semantic
    return {"scenario": item["scenario"], "mode": item["mode"],
            "evidence_sha256": fresh["evidence_sha256"],
            "attempt_metadata": read(directory / "attempt.json"),
            "objective_pass": objective, "semantic_pass": semantic,
            "constraint_pass": criteria["constraints"]["passed"],
            "decision_success": False if failed else objective if fixed else semantic,
            "task_applicable": applicable, "task_success": success,
            "status": "not_applicable" if not applicable else (
                "passed" if success is True else "failed" if success is False else "unscored"),
            "missing_report": not bool(report), "human_clarity": clarity,
            "business_unchanged": report.get("business_unchanged"),
            "invalid_calls": report.get("invalid_calls"),
            "elapsed_seconds": report.get("elapsed_seconds"),
            "actual_requests": report.get("actual_requests"),
            "model_calls": report.get("model_calls"),
            "reviewer": reviewer, "confirmation_extension": report.get("confirmation_passed"),
            "comparison_scope": "known_structured_intent" if fixed else (
                "decision_only" if not applicable else "diagnostic_task")}


def score_review(path):
    """Validate the review manifest and recompute ratings from original evidence."""
    review = read(path)
    if review["version"] != VERSION or review["criteria_definitions"] != CRITERIA:
        raise ValueError("Review version/rules mismatch")
    manifest = Path(review["manifest"])
    if digest(manifest) != review["manifest_sha256"]:
        raise ValueError("Trial manifest changed")
    original = read(manifest)["trials"]
    if len(original) != len(review["trials"]):
        raise ValueError("Scheduled trials must be retained")
    for old, new in zip(original, review["trials"], strict=True):
        for field in ("directory", "scenario", "mode", "rubric", "evidence_sha256"):
            if old[field] != new[field]:
                raise ValueError("Scheduled trial identity changed")
    directories = [Path(t["directory"]).resolve() for t in review["trials"]]
    if not directories or len(set(directories)) != len(directories):
        raise ValueError("Empty or duplicate trial list")
    return review, [score(t) for t in review["trials"]]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "score"))
    parser.add_argument("--trial", type=Path, action="append", default=[])
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "init":
        if not args.trial or args.review:
            parser.error("init requires --trial directories")
        directories = [p.resolve() for p in args.trial]
        if len(set(directories)) != len(directories):
            raise ValueError("Duplicate trial")
        if args.output.exists():
            raise FileExistsError(args.output)
        entries = [entry(p) for p in directories]
        manifest = args.output.with_suffix(".manifest.json")
        save(manifest, {"version": VERSION, "trials": entries})
        save(args.output, {"version": VERSION, "criteria_definitions": CRITERIA,
                           "manifest": str(manifest.resolve()), "manifest_sha256": digest(manifest),
                           "trials": entries})
    else:
        if not args.review or args.trial:
            parser.error("score requires --review")
        review, rows = score_review(args.review)
        save(args.output, {"version": VERSION, "review_sha256": digest(args.review),
             "reviewer_source_sha256": digest(Path(__file__)),
             "scope": "diagnostic_review_not_frozen_cohort", "p8_gate": "incomplete",
             "scheduled_trials": len(rows), "trials": rows,
             "counts": {s: sum(r["status"] == s for r in rows)
                        for s in ("passed", "failed", "unscored", "not_applicable")},
             "missing_reports": sum(r["missing_report"] for r in rows),
             "pooled_success_rate": None})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
