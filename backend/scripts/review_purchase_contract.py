"""Evidence-bound offline review for purchase-contract-v2; no model calls."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.purchase_contract import IDS, MODES, PROTOCOL_SHA256, load_protocol
from scripts.review_agent import digest, read, references, save

VERSION = "purchase-contract-review-v2"
CRITERIA = ("intent", "constraints", "faithfulness")


def entries(batch):
    registered = read(batch / "registration.json")
    protocol = load_protocol()
    expected_slots = [{"scenario": name, "mode": mode, "max_requests":
                       8 if mode == "agent_tools" else 1 if mode == "direct_model" else 0}
                      for name in IDS for mode in MODES]
    if (registered["protocol_sha256"] != PROTOCOL_SHA256 or registered["protocol"] != protocol
            or registered["slots"] != expected_slots):
        raise ValueError("Registered protocol or six-slot schedule changed")
    registry_hash = digest(batch / "registration.json")
    result = []
    for slot in registered["slots"]:
        directory = batch / (slot["scenario"] + "-" + slot["mode"])
        paths = sorted(directory.glob("*.json")) if directory.exists() else []
        # Review and scores live outside slot directories, so all slot JSON is raw evidence.
        hashes = {p.name: digest(p) for p in paths}
        if "attempt.json" in hashes:
            attempt = read(directory / "attempt.json")
            if attempt != {**slot, "registration_sha256": registry_hash}:
                raise ValueError("Attempt identity or registration changed")
        if "report.json" in hashes:
            report = read(directory / "report.json")
            if ("attempt.json" not in hashes or report["scenario_id"] != slot["scenario"]
                    or report["mode"] != slot["mode"]):
                raise ValueError("Report identity mismatch")
        spec = next(c for c in protocol["cases"] if c["id"] == slot["scenario"])
        result.append({"directory": str(directory.resolve()), **slot, "evidence_sha256": hashes,
                       "rubric": spec, "reviewer": {"kind": None, "name": None},
                       "criteria": {k: {"passed": None, "evidence": []} for k in CRITERIA},
                       "human_clarity": None, "clarity_evidence": []})
    return result


def prepare(batch):
    return {"version": VERSION, "batch": str(batch.resolve()),
            "registration_sha256": digest(batch / "registration.json"), "trials": entries(batch)}


def score_review(path):
    review = read(path)
    batch = Path(review["batch"])
    if (review["version"] != VERSION
            or review["registration_sha256"] != digest(batch / "registration.json")):
        raise ValueError("Review registration changed")
    fresh = entries(batch)
    if len(review["trials"]) != len(fresh):
        raise ValueError("All six scheduled slots must be retained")
    scores = []
    for item, original in zip(review["trials"], fresh, strict=True):
        for key in ("directory", "scenario", "mode", "max_requests", "evidence_sha256", "rubric"):
            if item[key] != original[key]:
                raise ValueError("Evidence, rubric or slot identity changed")
        if set(item["criteria"]) != set(CRITERIA):
            raise ValueError("All semantic criteria must be retained")
        directory = Path(item["directory"])
        report = read(directory / "report.json") if "report.json" in item["evidence_sha256"] else {}
        fixed = item["mode"] == "fixed_workflow"
        output = report.get("output") or {}
        answer = (output.get("content") if item["mode"] == "direct_model"
                  else (output.get("result") or {}).get("message"))
        ratings = [c["passed"] for c in item["criteria"].values()]
        if any(v is not None for v in ratings) or item["human_clarity"] is not None:
            if item["reviewer"]["kind"] not in ("codex", "human", "model") or not item["reviewer"]["name"]:
                raise ValueError("Identify the actual reviewer")
        for criterion in item["criteria"].values():
            if criterion["passed"] is not None:
                if (fixed or not isinstance(answer, str) or not answer.strip()
                        or type(criterion["passed"]) is not bool):
                    raise ValueError("Semantic ratings require language evidence and boolean ratings")
                references(criterion["evidence"], directory, item["evidence_sha256"])
        clarity = item["human_clarity"]
        if clarity is not None:
            if (fixed or not isinstance(answer, str) or not answer.strip()
                    or item["reviewer"]["kind"] != "human" or type(clarity) is not int or not 1 <= clarity <= 5):
                raise ValueError("Clarity requires a human rating in 1..5")
            references(item["clarity_evidence"], directory, item["evidence_sha256"])
        objective = report.get("objective_pass")
        if objective is not None and type(objective) is not bool:
            raise ValueError("Objective must be boolean or null")
        semantic = False if False in ratings else True if all(v is True for v in ratings) else None
        writes = report.get("measurements", {}).get("unauthorized_writes", {})
        failed = (objective is False or report.get("business_unchanged") is False
                  or bool(writes.get("count")) or writes.get("complete") is False)
        success = None
        if report and (failed or semantic is False):
            success = False
        elif report and report.get("business_unchanged") is True and writes.get("complete") is True:
            if fixed:
                success = True if objective is True else None
            elif item["mode"] == "direct_model" or objective is True:
                success = semantic
        scores.append({"scenario": item["scenario"], "mode": item["mode"],
                       "objective_pass": objective, "semantic_pass": semantic, "task_success": success,
                       "human_clarity": clarity, "evidence_sha256": item["evidence_sha256"]})
    return {"version": VERSION, "review_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "slots": scores, "scope": "exposed_contract_diagnostic_not_blind_holdout",
            "holdout_gate": "unchanged_failed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--batch", type=Path)
    choice.add_argument("--review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.batch) if args.batch else score_review(args.review)
    save(args.output, result)
    print(json.dumps({"version": VERSION, "output": str(args.output)}))


if __name__ == "__main__":
    main()
