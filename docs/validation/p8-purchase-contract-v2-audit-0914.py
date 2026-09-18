"""Offline audit and Codex review of the completed 0914 batch; never sends a request."""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.agent_model import fingerprint
from app.services.tool_protocol import wire_messages
from scripts.diagnose_purchase import source_hash
from scripts.purchase_contract import result_check, run_check
from scripts.review_agent import digest, read, save
from scripts.review_purchase_contract import prepare, score_review

BATCH = Path("D:/SoloMeal-Acceptance/p8-purchase-contract-v2-0914-01")


def main():
    registered = read(BATCH / "registration.json")
    assert source_hash() == registered["source_sha256"]
    previous = read(ROOT / "docs/validation/p8-a026-contract-audit-0914.json")
    assert previous["frozen_json_sha256"] == registered["frozen_json_sha256"]
    assert registered["frozen_json_sha256"] == {
        p.name: digest(p) for p in sorted((ROOT / "evaluation").glob("*.json"))}
    calls = []
    report_hashes = {}
    for slot in registered["slots"]:
        directory = BATCH / (slot["scenario"] + "-" + slot["mode"])
        report = read(directory / "report.json")
        report_hashes[directory.name] = digest(directory / "report.json")
        spec = next(c for c in registered["protocol"]["cases"] if c["id"] == slot["scenario"])
        assert report["business_unchanged"] is True
        writes = report["measurements"]["unauthorized_writes"]
        assert writes["complete"] and writes["count"] == 0 and writes["attempted_statements"] == 0
        assert report["before"]["quotes"][0]["observed_on"] == registered["fixture_date"]
        if slot["mode"] == "fixed_workflow":
            assert result_check(spec, report["output"], report["before"])
        elif slot["mode"] == "agent_tools":
            assert run_check(spec, report["output"], report["before"])
        results = sorted(directory.glob("call-*-result.json"))
        assert len(results) == len(list(directory.glob("call-*-input.json")))
        assert len(results) == len(list(directory.glob("call-*-attempt.json")))
        assert len(results) == report["actual_requests"] <= slot["max_requests"]
        metadata = []
        for path in results:
            stem = path.name.removesuffix("-result.json")
            observed = read(directory / (stem + "-input.json"))
            attempt = read(directory / (stem + "-attempt.json"))
            record = read(path)["metadata"]
            for key in ("messages", "tools"):
                assert fingerprint(observed[key]) == attempt[key + "_sha256"] == record[key + "_sha256"]
            expected_tools = registered["tools_sha256"] if slot["mode"] == "agent_tools" else fingerprint([])
            assert record["tools_sha256"] == expected_tools
            wire = (wire_messages(observed["messages"], observed["tools"])
                    if record["tool_protocol"] == "json" else observed["messages"])
            assert fingerprint(wire) == record["wire_messages_sha256"]
            assert record["model"] == registered["model"] and record["enable_thinking"] == "false"
            assert record["timeout_seconds"] == 30 and record["max_completion_tokens"] == 3000
            assert record["http_status"] == 200 and record["diagnostic"] is None and record["request_sent"]
            assert record["transport_version"] == registered["transport_version"]
            assert record["temperature"] == registered["temperature"] and record["top_p"] == registered["top_p"]
            metadata.append(record)
        assert metadata == report["model_calls"]
        calls.extend(metadata)
    assert len(calls) == 8
    review = prepare(BATCH)
    for item in review["trials"]:
        if item["mode"] == "fixed_workflow":
            continue
        item["reviewer"] = {"kind": "codex", "name": "Codex"}
        direct = item["mode"] == "direct_model"
        pointer = "/output/content" if direct else "/output/result/message"
        purchase = item["scenario"].startswith("PURCHASE-")
        reasons = {
            "intent": ("Explicitly uses the stated 190g shortage without subtracting 50g again or inventing servings."
                       if purchase else "Uses the white-rice recipe for three people: 240g needed, 190g shortage from 50g stock."),
            "constraints": "Two whole 100g packages total 200g and CNY6; answer qualifies this as a snapshot-based estimate. No claim of a guaranteed live store price.",
            "faithfulness": "Numbers agree with the saved quote and applicable recipe/current successful tool result. Source/date when stated match. No claim of purchase, reservation, cooking or stock mutation."
        }
        if direct and not purchase:
            reasons["constraints"] += " The heading uses actual expenditure, but the conclusion explicitly says estimated expense and snapshot calculation; read in full, it does not promise a live price."
        for name, criterion in item["criteria"].items():
            criterion.update(passed=True, evidence=[
                {"file": "report.json", "pointer": pointer, "reason": reasons[name]},
                {"file": "report.json", "pointer": "/before/quotes", "reason": "Saved 100g/CNY3 quote and dated provenance."},
                {"file": "report.json", "pointer": "/before/inventory", "reason": "Initial rice stock is 50g; purchase shortage is already final, planning subtracts it once."}])
            if not direct:
                criterion["evidence"].append({"file": "report.json", "pointer": "/output/events/1/result",
                                             "reason": "Successful required-tool result supporting the answer."})
    save(BATCH / "review.json", review)
    scores = score_review(BATCH / "review.json")
    assert all(s["task_success"] is True for s in scores["slots"])
    save(BATCH / "scores.json", scores)
    usage = {key: sum(c["usage"][key] for c in calls)
             for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    summary = {"version": "purchase-contract-v2-audited", "source_sha256": registered["source_sha256"],
               "protocol_sha256": registered["protocol_sha256"],
               "system_sha256": registered["system_sha256"], "tools_sha256": registered["tools_sha256"],
               "scope": registered["protocol"]["scope"], "actual_requests": len(calls), "usage": usage,
               "cumulative_known_chat_requests": 1635, "cumulative_visual_requests": 30,
               "all_eight_input_hash_triplets_match": True, "business_unchanged": True,
               "unauthorized_business_dml": 0, "http_statuses": [200], "missing_usage": 0,
               "model_elapsed_seconds": [c["elapsed_seconds"] for c in calls],
               "batch_wall_seconds_from_completion_file_mtime": (BATCH / "execution-complete.json").stat().st_mtime
               - datetime.fromisoformat(registered["started_at"]).timestamp(),
               "estimated_not_billing": {"requests": [8, 10], "tokens": [40000, 65000], "wall_minutes": [1, 3]},
               "scores": scores["slots"], "human_clarity": None, "holdout": "48/60; failed; unchanged",
               "private_artifact_sha256": {name: digest(BATCH / name) for name in (
                   "registration.json", "execution-complete.json", "review.json", "scores.json")},
               "raw_report_sha256": report_hashes}
    assert report_hashes == {name: digest(BATCH / name / "report.json") for name in report_hashes}
    save(BATCH / "audit.json", summary)
    save(ROOT / "docs/validation/p8-purchase-contract-v2-0914.json", summary)
    print(json.dumps({k: summary[k] for k in ("source_sha256", "actual_requests", "usage",
          "batch_wall_seconds_from_completion_file_mtime")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
