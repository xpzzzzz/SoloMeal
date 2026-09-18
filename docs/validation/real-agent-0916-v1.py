"""Bounded, separately registered real-model diagnostics and local UI acceptance."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings
from app.services.agent import PROMPT_VERSION, SYSTEM, tools
from app.services.agent_model import ChatModel, fingerprint
from scripts.diagnose_purchase import source_hash
from scripts.evaluate_agent import advance_run, isolated_client, request, save, seed, snapshot
from scripts.evaluation_measurements import WriteObserver
from scripts.purchase_contract import BoundedModel

PROTOCOL = {
    "version": "real-agent-diagnostic-0916-v1", "scope": "exposed_regression_not_holdout",
    "retries": 0, "timeout_seconds": 30, "max_completion_tokens": 3000,
    "diagnostic_max_requests": 32, "page_max_requests": 24,
    "multi": ["推荐25分钟内的一人餐。", "改成三人份，其余不变。", "时间改成15分钟，其余不变。"],
    "multi_expected": [{"servings": 1, "max_minutes": 25},
                       {"servings": 3, "max_minutes": 25},
                       {"servings": 3, "max_minutes": 15}],
    "recovery": "请规划三份白米饭，最多补购6元，按已保存的报价计算整包支出，说明报价来源和日期。只查询，不创建方案或入库。",
    "fault": {"tool": "recommend_meal", "arguments": {"servings": 3, "budget": "6",
              "quotes": [{"source": "INJECTED_UNTRUSTED_SHOP", "observed_on": "1999-01-01"}]}},
    "fault_scope": "one_scripted_invalid_call_then_real_model_recovery_not_spontaneous_model_error",
    "page_prompts": ["给大米入库100克，先让我确认。", "白米饭一人份已经做完，请记录，先让我确认。",
                     "刚才的白米饭记录错了，请撤销刚才那次做饭，先让我确认。"],
    "page_expected_rice": [300, 400, 320, 400],
    "page_checks": ["preview_no_business_write", "refresh_relogin_preserves_pending_id",
                    "explicit_approval_exact_delta", "cooking_retracted_and_consumption_restored"],
    "human_clarity": None, "holdout_gate": "unchanged_failed",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def register(folder, mode, settings):
    folder.mkdir(parents=True, exist_ok=False)
    save(folder / "registration.json", {
        "started_at": datetime.now(timezone.utc).isoformat(), "mode": mode,
        "protocol": PROTOCOL, "protocol_sha256": fingerprint(PROTOCOL),
        "driver_sha256": digest(Path(__file__)), "source_sha256": source_hash(),
        "prompt_version": PROMPT_VERSION, "system_sha256": fingerprint(SYSTEM),
        "tools_sha256": fingerprint(tools()), "model": settings.model_name,
        "tool_protocol": "json", "enable_thinking": False,
        "frozen_json": {p.name: digest(p) for p in sorted((ROOT / "evaluation").glob("*.json"))},
    })


class InjectOnce:
    def __init__(self, inner):
        self.inner, self.used = inner, False

    def complete(self, messages, definitions):
        if self.used:
            return self.inner.complete(messages, definitions)
        self.used = True
        fault = PROTOCOL["fault"]
        return {"tool_calls": [{"id": "controlled-rejected-quote", "type": "function",
                "function": {"name": fault["tool"], "arguments": json.dumps(fault["arguments"])}}]}


def diagnostic(folder, settings):
    for name in ("multi", "recovery"):
        directory = folder / name
        directory.mkdir()
        model = BoundedModel(ChatModel(settings), directory, 24 if name == "multi" else 8)
        with isolated_client(settings) as client:
            headers = seed(client, "standard" if name == "multi" else "low_stock_quoted")
            before = snapshot(client, headers)
            runs, checks = [], []
            with WriteObserver(client.app.state.engine) as observer:
                client.app.state.evaluation_observer = observer
                observer.active = True
                client.app.state.agent_model = model if name == "multi" else InjectOnce(model)
                prompts = PROTOCOL["multi"] if name == "multi" else [PROTOCOL["recovery"]]
                for index, prompt in enumerate(prompts):
                    run = advance_run(client, headers, prompt, runs[-1] if runs else None)
                    runs.append(run)
                    save(directory / f"turn-{index + 1}.json", run)
                    successful = [e for e in run["events"] if e["tool"] == "recommend_meal"
                                  and "error" not in e["result"]]
                    ok = run["status"] == "completed" and bool(successful) and not run["pending"]
                    if name == "multi":
                        expected = PROTOCOL["multi_expected"][index]
                        ok = ok and all(all(e["result"]["constraints"].get(k) == v
                                            for k, v in expected.items()) for e in successful)
                        if index == 2:
                            excerpts = run["context_summary"]["excerpts"]
                            ok = ok and len(excerpts) == 4 and "历史对话摘录" not in json.dumps(excerpts, ensure_ascii=False)
                    else:
                        error = run["events"][0]["result"].get("error", {})
                        ok = ok and error.get("code") == "INVALID_TOOL_ARGUMENTS"
                        ok = ok and "recovery" not in error and "INJECTED_UNTRUSTED_SHOP" not in json.dumps(error)
                    checks.append(bool(ok))
                    if run["status"] != "completed":
                        break
                after = snapshot(client, headers)
                immutable = all(request(client, "GET", f"agent/runs/{r['id']}", headers) == r for r in runs[:-1])
                writes = observer.result()
                save(directory / "report.json", {
                    "checks": checks, "objective_pass": all(checks) and len(runs) == len(prompts)
                    and before == after and immutable and writes["count"] == 0 and writes["complete"],
                    "before": before, "after": after, "parent_runs_unchanged": immutable,
                    "writes": writes, "requests": len(model.records), "model_calls": model.records,
                    "semantic_review": None, "human_clarity": None,
                })
                del client.app.state.evaluation_observer
        print(json.dumps({"slot": name, "checks": checks, "requests": len(model.records)}), flush=True)


def serve(folder, settings, port):
    import uvicorn
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles

    class FixtureCredentials:
        def __init__(self, client):
            self.client = client

        def request(self, method, path, **kwargs):
            if path in ("/api/v1/auth/register", "/api/v1/auth/login"):
                kwargs["json"] = {"username": "real_ui_0916", "password": "Synthetic-ui-0916-only"}
            return self.client.request(method, path, **kwargs)

        @property
        def app(self):
            return self.client.app

    with isolated_client(settings) as client:
        headers = seed(FixtureCredentials(client), "standard")
        save(folder / "before.json", snapshot(client, headers))
        client.app.state.agent_model = BoundedModel(ChatModel(settings), folder, 24)
        dist = ROOT / "frontend/dist"

        @client.app.get("/", response_class=HTMLResponse)
        def index():
            return (dist / "index.html").read_text(encoding="utf-8")

        client.app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        try:
            uvicorn.run(client.app, host="127.0.0.1", port=port, access_log=False)
        finally:
            save(folder / "after.json", snapshot(client, headers))
            summaries = request(client, "GET", "agent/runs", headers)
            save(folder / "runs.json", [request(client, "GET", f"agent/runs/{r['id']}", headers) for r in summaries])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("diagnostic", "serve"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8016)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(ROOT):
        parser.error("Private evidence must be outside repository")
    settings = Settings().model_copy(update={"agent_enabled": True, "model_tool_protocol": "json",
        "model_enable_thinking": False, "model_max_completion_tokens": 3000, "receipt_vision_enabled": False})
    register(args.output, args.mode, settings)
    if args.mode == "diagnostic":
        diagnostic(args.output, settings)
    else:
        serve(args.output, settings, args.port)


if __name__ == "__main__":
    main()
