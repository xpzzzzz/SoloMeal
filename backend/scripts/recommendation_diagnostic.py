"""Four bounded exposed-regression turns; model prose and product prose stay separate."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.services.agent import PROMPT_VERSION, SYSTEM, tools
from app.services.agent_model import ChatModel, fingerprint
from scripts.diagnose_purchase import source_hash
from scripts.evaluate_agent import advance_run, isolated_client, request, save, seed, snapshot
from scripts.evaluation_measurements import QUERY_TOOLS, WriteObserver
from scripts.purchase_contract import BoundedModel

PROTOCOL = {
    "version": "recommendation-response-diagnostic-v1", "scope": "exposed_regression_not_holdout",
    "fixture": "standard", "initial_rice_g": 300, "initial_eggs": 2,
    "prompts": ["推荐25分钟内的一人餐。", "改成三人份，其余不变。",
                "时间改成15分钟，其余不变。", "我已补充并确认入库1个鸡蛋，请按刚才三人份、15分钟的条件重新查询。"],
    "expected": [[1, 25, True], [3, 25, False], [3, 15, False], [3, 15, True]],
    "driver_mutation_before_turn": 4, "driver_mutation": {"name": "鸡蛋", "quantity": "1", "unit": "piece"},
    "max_requests": 32, "retries": 0, "timeout_seconds": 30, "max_completion_tokens": 3000,
    "semantic_rubric": ["Match current servings, time and tool quantities; do not reuse old amounts.",
                        "Missing eggs means purchase and confirm inventory before a new cooking preview.",
                        "No claims of existing preview, purchase, cooking or inventory mutation by the Agent.",
                        "Only tool-backed facts and capability claims; model and product judged independently."],
    "human_clarity": None, "holdout_gate": "unchanged_failed",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def register(folder, settings):
    folder.mkdir(parents=True, exist_ok=False)
    paths = [*sorted((ROOT.parent / "frontend/src").glob("*")),
             *sorted((ROOT.parent / "frontend/dist").rglob("*")),
             *sorted((ROOT.parent / "evaluation").glob("*.json"))]
    registration = {"started_at": datetime.now(timezone.utc).isoformat(),
        "protocol": PROTOCOL, "protocol_sha256": fingerprint(PROTOCOL),
        "driver_sha256": digest(Path(__file__)), "source_sha256": source_hash(),
        "prompt_version": PROMPT_VERSION, "system_sha256": fingerprint(SYSTEM),
        "tools_sha256": fingerprint(tools()), "model": settings.model_name,
        "tool_protocol": "json", "enable_thinking": False,
        "files": {p.relative_to(ROOT.parent).as_posix(): digest(p) for p in paths if p.is_file()}}
    save(folder / "registration.json", registration)
    return registration


def check_turn(run, index):
    """Objective checks only: no keyword-based automatic semantic pass."""
    try:
        servings, minutes, enabled = PROTOCOL["expected"][index]
        event = run["events"][-1]
        result = event["result"]
        final = run["result"]
        egg = next(c for c in result["candidates"] if c["recipe"]["name"] == "蛋炒饭")
        actions = final["next_actions"]
        action = next(a for a in actions if a["recipe_id"] == egg["recipe"]["id"])
        required = {i["name"]: Decimal(i["quantity"]) for i in egg["required_ingredients"]}
        missing = {i["name"]: Decimal(i["missing_quantity"]) for i in egg["shopping"]}
        names = {c["recipe"]["name"] for c in result["candidates"]}
        return (run["status"] == "completed" and not run["pending"]
            and all(e["tool"] in QUERY_TOOLS for e in run["events"])
            and event["tool"] == "recommend_meal" and "error" not in result
            and result["constraints"]["servings"] == servings
            and result["constraints"]["max_minutes"] == minutes
            and names == ({"蛋炒饭", "白米饭"} if minutes == 25 else {"蛋炒饭"})
            and egg["servings"] == servings and required == {"大米": Decimal(80 * servings), "鸡蛋": Decimal(servings)}
            and missing == ({} if enabled else {"鸡蛋": Decimal(1)})
            and egg["can_cook_now"] is enabled and action["prepare_cooking"]["enabled"] is enabled
            and len(actions) == len(result["candidates"])
            and final["response_source"] == "recommendation-response-v1"
            and final["source_step"] == event["step"]
            and isinstance(final["model_message"], str) and bool(final["model_message"])
            and run["messages"][-1]["content"] == final["message"])
    except (KeyError, IndexError, TypeError, StopIteration, ValueError):
        return False


def trial(client, folder, model):
    headers = seed(client, "standard")
    runs, checks, unchanged = [], [], []
    with WriteObserver(client.app.state.engine) as observer:
        client.app.state.evaluation_observer = observer
        observer.active = True
        client.app.state.agent_model = model
        for index, prompt in enumerate(PROTOCOL["prompts"]):
            if index == 3:
                prior = snapshot(client, headers)
                egg = next(i for i in request(client, "GET", "ingredients", headers) if i["name"] == "鸡蛋")
                mutation = request(client, "POST", "inventory",
                    {**headers, "Idempotency-Key": uuid4().hex},
                    {"ingredient_id": egg["id"], "quantity": "1", "unit": "piece"}, driver_write=True)
                after = snapshot(client, headers)
                save(folder / "driver-stock-in.json", {"before": prior, "response": mutation, "after": after,
                     "scope": "explicit_fixture_API_write_not_model_or_UI_action"})
            before = snapshot(client, headers)
            run = advance_run(client, headers, prompt, runs[-1] if runs else None, retries=0)
            runs.append(run)
            after = snapshot(client, headers)
            unchanged.append(before == after)
            checks.append(check_turn(run, index))
            save(folder / f"turn-{index + 1}.json", {"run": run, "before": before, "after": after,
                "objective_pass": checks[-1], "model_semantic_pass": None, "product_semantic_pass": None})
            print(json.dumps({"turn": index + 1, "status": run["status"], "objective_pass": checks[-1]}), flush=True)
            if run["status"] != "completed":
                break
        reread = [request(client, "GET", f"agent/runs/{r['id']}", headers) for r in runs]
        immutable = all(all(old[k] == new[k] for k in old if k not in ("session_version", "latest_run_id"))
                        for old, new in zip(runs, reread, strict=True))
        save(folder / "reread.json", reread)
        writes = observer.result()
        report = {"checks": checks, "business_unchanged_per_turn": unchanged,
            "runs_unchanged": immutable, "writes": writes, "requests": len(model.records),
            "model_calls": model.records, "objective_pass": len(runs) == 4 and all(checks) and all(unchanged)
            and immutable and writes["count"] == 0 and writes["complete"],
            "model_semantic_pass": None, "product_semantic_pass": None, "human_clarity": None}
        save(folder / "report.json", report)
        del client.app.state.evaluation_observer
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--send-model", action="store_true", required=True)
    args = parser.parse_args()
    folder = args.output.resolve()
    if folder.is_relative_to(ROOT.parent):
        parser.error("Private evidence must be outside repository")
    settings = Settings().model_copy(update={"agent_enabled": True, "model_tool_protocol": "json",
        "model_enable_thinking": False, "model_max_completion_tokens": 3000, "receipt_vision_enabled": False})
    register(folder, settings)
    model = BoundedModel(ChatModel(settings), folder, 32)
    with isolated_client(settings) as client:
        report = trial(client, folder, model)
    save(folder / "completion.json", {"completed_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": source_hash(), "objective_pass": report["objective_pass"]})


if __name__ == "__main__":
    main()
