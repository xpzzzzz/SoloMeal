"""One registered purchase-shape diagnostic, separate from the frozen P8 dataset."""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.services.agent import PROMPT_VERSION, SYSTEM, tools
from app.services.agent_model import ChatModel, fingerprint
from scripts.evaluate_agent import (
    RecordedModel,
    advance_run,
    isolated_client,
    save,
    seed,
    snapshot,
)
from scripts.evaluation_measurements import QUERY_TOOLS, WriteObserver, measurements

PROTOCOL = ROOT.parent / "docs/validation/p8-purchase-v21-diagnostic-protocol.json"
NUMERIC_FIELDS = {"shortage_quantity", "purchase_quantity", "estimated_cost", "budget"}


def source_hash():
    digest = hashlib.sha256()
    for path in sorted([*ROOT.glob("app/**/*.py"), *ROOT.glob("scripts/**/*.py")]):
        digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def purchase_check(run, quote, expected):
    successes = [e for e in run["events"] if e["tool"] == "estimate_purchase"
                 and isinstance(e.get("result"), dict) and "error" not in e["result"]]
    matches = []
    for event in successes:
        result = event["result"]
        matches.append(
            result.get("ingredient", {}).get("id") == quote["ingredient_id"]
            and all((result.get(key) is not None
                     and Decimal(str(result[key])) == Decimal(str(value)))
                    if key in NUMERIC_FIELDS else result.get(key) == value
                    for key, value in expected.items())
            and result.get("source") == quote["source"]
            and result.get("observed_on") == quote["observed_on"]
            and Decimal(str(event["arguments"].get("budget", -1))) == Decimal("6")
        )
    return (run["status"] == "completed" and bool(matches) and all(matches)
            and not run.get("pending")
            and all(e["tool"] in QUERY_TOOLS for e in run["events"]))


def purchase_trial(client, model, protocol):
    spec = protocol["new_shape"]
    headers = seed(client, spec["fixture"])
    before = snapshot(client, headers)
    quote = next(q for q in before["quotes"] if q["package_quantity"] == "100.000")
    with WriteObserver(client.app.state.engine) as observer:
        client.app.state.evaluation_observer = observer
        observer.active = True
        client.app.state.agent_model = model
        started = time.perf_counter()
        try:
            run = advance_run(client, headers, spec["prompt"])
            unchanged = before == snapshot(client, headers)
            result = {
                "scenario_id": spec["id"], "mode": "agent_tools", "split": "diagnostic",
                "scope": "new_purchase_shape_not_frozen_holdout", "fixture": spec["fixture"],
                "prompt": spec["prompt"], "saved_quote": quote, "output": run,
                "objective_pass": purchase_check(run, quote, spec["expected_result"]) and unchanged,
                "business_unchanged": unchanged, "confirmation_extension": None,
                "confirmation_passed": None, "human_clarity": None, "task_success": None,
                "elapsed_seconds": time.perf_counter() - started,
                "model_calls": list(model.records), "actual_requests": len(model.records),
                "required_query": ["estimate_purchase"],
            }
            result["measurements"] = measurements(result, observer)
            if observer.result()["count"] or not observer.result()["complete"]:
                result["objective_pass"] = False
            return result
        finally:
            del client.app.state.evaluation_observer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--send-model", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not args.send_model or output.is_relative_to(ROOT.parent):
        parser.error("Requires --send-model and a new private directory outside the repository")
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    settings = Settings().model_copy(update={"agent_enabled": True, "model_tool_protocol": "json",
        "model_enable_thinking": False, "model_max_completion_tokens": 3000})
    output.mkdir(parents=True, exist_ok=False)
    save(output / "attempt.json", {
        "scenario": protocol["new_shape"]["id"], "mode": "agent_tools",
        "source_sha256": source_hash(), "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        "prompt_version": PROMPT_VERSION, "system_sha256": fingerprint(SYSTEM),
        "tools_sha256": fingerprint(tools()), "tool_protocol": "json", "enable_thinking": "false",
        "max_completion_tokens": 3000, "model_timeout_seconds": 30,
        "confirmation_extension": "none", "max_requests": 8, "retries": 0,
        "started_at": datetime.now(timezone.utc).isoformat(), "scope": "new_shape_diagnostic"})
    with isolated_client(settings) as client:
        result = purchase_trial(client, RecordedModel(ChatModel(settings), output), protocol)
    save(output / "report.json", result)
    print(json.dumps({k: result[k] for k in ("scenario_id", "objective_pass", "actual_requests")}))
    return 0 if result["objective_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
