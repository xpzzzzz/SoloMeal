"""Bounded A014 v8 final-request replay; diagnostic only, no tool execution."""

import argparse
import hashlib
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

VERSION = "a014-timeout-probe-v1"


def reconstructed(source):
    report = json.loads((source / "report.json").read_text(encoding="utf-8"))
    old = json.loads((source / "call-02-result.json").read_text(encoding="utf-8"))["metadata"]
    if (report["scenario_id"] != "A014" or report["actual_requests"] != 2
            or old["diagnostic"] != "timeout" or old["protocol_version"] != "json-tools-v2"
            or old["max_completion_tokens"] != 1500 or old["timeout_seconds"] != 30
            or old["enable_thinking"] != "not_sent"):
        raise ValueError("Expected A014 second-request timeout with original parameters")
    run = report["output"]
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content":
        "当前结构化规划条件（保持未修改项；只有用户提出变更时才更新）："
        + json.dumps(run["constraints"], ensure_ascii=False)}, *run["messages"]]
    definitions = tools()
    wire = tool_protocol.wire_messages(messages, definitions)
    for key, value in (("messages_sha256", messages), ("tools_sha256", definitions),
                       ("wire_messages_sha256", wire)):
        if fingerprint(value) != old[key]:
            raise ValueError("Replay inputs differ; no request allowed")
    return wire, old


def request(settings, wire, timeout, directory, name, *, transport=None, max_completion_tokens=1500):
    payload = {"model": settings.model_name, "messages": wire,
               "max_completion_tokens": max_completion_tokens, "response_format": {"type": "json_object"}}
    save(directory / f"{name}-attempt.json", {"payload_sha256": fingerprint(payload),
         "timeout_seconds": timeout, "max_completion_tokens": max_completion_tokens,
         "enable_thinking": "not_sent", "model": settings.model_name})
    result = {"valid_final": False, "diagnostic": None, "usage": usage_metadata(None),
              "request_attempted": True, "http_status": None}
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, transport=transport) as client:
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
        result["valid_final"] = bool(result["decoded"].get("content"))
        if not result["valid_final"]:
            result["diagnostic"] = "non_final_response"
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError, AttributeError) as exc:
        result["diagnostic"] = failure_category(exc)
    result["elapsed_seconds"] = time.perf_counter() - started
    save(directory / f"{name}-result.json", result)
    return result


def run(settings, wire, directory, *, transport=None):
    results = [request(settings, wire, 60, directory, "replay", transport=transport)]
    if not results[0]["valid_final"]:
        healthy = [{"role": "user", "content":
                    'Return exactly this JSON object: {"kind":"final","content":"ok"}'}]
        results.append(request(settings, healthy, 30, directory, "health", transport=transport))
    save(directory / "report.json", {"version": VERSION, "results": results,
         "actual_requests": len(results), "business_execution": False,
         "p8_gate": "incomplete", "cost": None})
    return results


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
    save(args.output / "probe.json", {"version": VERSION, "source": str(args.source),
         "source_report_sha256": hashlib.sha256((args.source / "report.json").read_bytes()).hexdigest(),
         "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         "original_metadata": old, "three_input_hashes_verified": True,
         "maximum_requests": 2, "scope": "no_business_execution"})
    results = run(settings, wire, args.output)
    print(json.dumps([{k: r[k] for k in ("valid_final", "diagnostic", "elapsed_seconds", "usage")}
                      for r in results]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
