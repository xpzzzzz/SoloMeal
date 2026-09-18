"""Single-variable A014 replay: remove only tool-schema JSON whitespace."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.services import tool_protocol
from app.services.agent import SYSTEM, tools
from app.services.agent_model import fingerprint
from scripts.evaluate_agent import save
from scripts.probe_a014_timeout import request

VERSION = "a014-schema-whitespace-v1"


def reconstructed(source):
    report = json.loads((source / "report.json").read_text(encoding="utf-8"))
    old = json.loads((source / "call-01-result.json").read_text(encoding="utf-8"))["metadata"]
    if (report["scenario_id"] != "A014" or report["actual_requests"] != 1
            or report["mode"] != "agent_tools" or report["output"]["events"]
            or old["diagnostic"] != "timeout" or old["protocol_version"] != "json-tools-v2"
            or old["max_completion_tokens"] != 3000 or old["timeout_seconds"] != 30
            or old["enable_thinking"] != "not_sent"):
        raise ValueError("Expected the original A014 first-request timeout")
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


def compact(wire):
    prefix = tool_protocol.INSTRUCTION
    if wire[0]["role"] != "system" or not wire[0]["content"].startswith(prefix):
        raise ValueError("Expected complete protocol instruction and schema")
    original = wire[0]["content"][len(prefix):]
    definitions = tool_protocol.strict_json(original)
    text = json.dumps(definitions, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    result = [{**wire[0], "content": prefix + text}, *wire[1:]]
    return result, {
        "schema_equal": tool_protocol.strict_json(text) == definitions,
        "other_messages_equal": result[1:] == wire[1:],
        "schema_characters_before": len(original), "schema_characters_after": len(text),
        "wire_content_characters_before": sum(len(m["content"] or "") for m in wire),
        "wire_content_characters_after": sum(len(m["content"] or "") for m in result),
        "baseline_wire_sha256": fingerprint(wire), "variant_wire_sha256": fingerprint(result),
    }


def run(settings, wire, directory, *, transport=None):
    variant, analysis = compact(wire)
    save(directory / "analysis.json", analysis)
    result = request(settings, variant, 30, directory, "replay", transport=transport,
                     max_completion_tokens=3000)
    # A first request should select a tool; the shared final-probe label is not task success.
    decoded = result.get("decoded", {})
    calls = decoded.get("tool_calls", [])
    expected = (len(calls) == 1 and calls[0]["function"]["name"] == "recommend_meal")
    save(directory / "report.json", {"version": VERSION, "actual_requests": 1,
         "maximum_requests": 1, "business_execution": False, "task_success": None,
         "expected_tool_selected": expected, "result": result,
         "p8_gate": "incomplete", "cost": None})
    return {"expected_tool_selected": expected, **{k: result[k] for k in (
        "diagnostic", "elapsed_seconds", "usage", "http_status")}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--send-model", action="store_true")
    args = parser.parse_args(argv)
    wire, old = reconstructed(args.source)
    if not args.send_model:
        print(json.dumps(compact(wire)[1]))
        return 0
    if args.output.resolve().is_relative_to(ROOT.parent):
        parser.error("Private output outside repository required")
    settings = Settings()
    if (settings.model_name != old["model"] or not settings.model_api_key
            or not settings.model_api_key.get_secret_value()):
        parser.error("Configured original model and credential required")
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output / "probe.json", {"version": VERSION, "source": str(args.source),
         "original_metadata": old, "three_input_hashes_verified": True,
         "maximum_requests": 1, "scope": "no_business_execution",
         "files_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in {
             "source_report": args.source / "report.json", "script": Path(__file__),
             "transport": Path(__file__).with_name("probe_a014_timeout.py")}.items()}})
    print(json.dumps(run(settings, wire, args.output)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
