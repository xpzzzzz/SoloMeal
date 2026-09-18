"""Replay the recorded A014 first request with two output limits, without tools execution."""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from app.core.config import Settings
from app.services import tool_protocol
from app.services.agent import SYSTEM, tools
from app.services.agent_model import failure_category, fingerprint, usage_metadata
from scripts.evaluate_agent import save


def reconstructed(source):
    report = json.loads((source / "report.json").read_text(encoding="utf-8"))
    old = json.loads((source / "call-01-result.json").read_text(encoding="utf-8"))["metadata"]
    if report["scenario_id"] != "A014" or report["actual_requests"] != 1:
        raise ValueError("Expected the single-request A014 diagnostic")
    run = report["output"]
    system_v4 = SYSTEM.split("入库数量只有数字没有计量单位时，", 1)[0]
    messages = [{"role": "system", "content": system_v4}, {"role": "user", "content":
        "当前结构化规划条件（保持未修改项；只有用户提出变更时才更新）："
        + json.dumps(run["constraints"], ensure_ascii=False)}, *run["messages"]]
    definitions = tools()
    wire = tool_protocol.wire_messages(messages, definitions)
    if (fingerprint(messages) != old["messages_sha256"]
            or fingerprint(definitions) != old["tools_sha256"]
            or fingerprint(wire) != old["wire_messages_sha256"]):
        raise ValueError("Replay inputs differ from original; no model call allowed")
    return wire, old


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--send-model", action="store_true")
    args = parser.parse_args(argv)
    if not args.send_model or args.output.resolve().is_relative_to(ROOT.parent):
        parser.error("Explicit --send-model and private output outside repository required")
    wire, old = reconstructed(args.source)
    settings = Settings()
    if settings.model_name != old["model"]:
        parser.error("Model must match original")
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output / "probe.json", {"scope": "no_business_execution", "limits": [1500, 3000],
         "source": str(args.source), "wire_messages_sha256": fingerprint(wire),
         "model": settings.model_name, "timeout_seconds": 30, "enable_thinking": "not_sent"})
    results = []
    for limit in (1500, 3000):
        payload = {"model": settings.model_name, "messages": wire,
                   "max_completion_tokens": limit, "response_format": {"type": "json_object"}}
        save(args.output / f"limit-{limit}-attempt.json", {"payload_sha256": fingerprint(payload)})
        result = {"limit": limit, "usage": usage_metadata(None), "valid_response": False,
                  "request_attempted": True, "diagnostic": None}
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                response = client.post(settings.model_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + settings.model_api_key.get_secret_value()}, json=payload)
                result["http_status"] = response.status_code
                response.raise_for_status()
                body = response.json()
            result["usage"] = usage_metadata(body.get("usage"))
            choice = body["choices"][0]
            result["finish_reason"] = choice.get("finish_reason")
            message = choice["message"]
            result["provider_message"] = {k: message[k] for k in ("role", "content", "tool_calls") if k in message}
            result["decoded"] = tool_protocol.decode(message)
            result["valid_response"] = True
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            result["diagnostic"] = failure_category(exc)
        result["elapsed_seconds"] = time.perf_counter() - started
        save(args.output / f"limit-{limit}-result.json", result)
        results.append(result)
    save(args.output / "report.json", {"results": results, "business_execution": False})
    print(json.dumps([{k: r[k] for k in ("limit", "valid_response", "diagnostic", "usage")} for r in results]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
