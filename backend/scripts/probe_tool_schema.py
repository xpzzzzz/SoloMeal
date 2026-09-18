"""Controlled schema-only diagnostics: identical messages and tool set, no business execution."""

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.schemas.planning import PlanningInput
from app.services.agent import PROMPT_VERSION, SYSTEM, tools
from app.services.agent_model import ChatModel, ModelCallError, fingerprint
from pydantic import ValidationError
from scripts.evaluate_agent import RecordedModel, save


def transform(definitions, profile):
    def visit(node, root, stack=()):
        if isinstance(node, list):
            return [visit(x, root, stack) for x in node]
        if not isinstance(node, dict):
            return node
        node = dict(node)
        if profile == "no_defaults":
            node.pop("default", None)
        if profile == "inline_refs" and "$ref" in node:
            ref = node.pop("$ref")
            if not ref.startswith("#/$defs/") or ref in stack:
                raise ValueError("Only acyclic local definitions are supported")
            target = root["$defs"][ref.removeprefix("#/$defs/")]
            if (set(target) & set(node)) - {"title", "description", "default"}:
                raise ValueError("Conflicting reference siblings")
            return visit({**target, **node}, root, (*stack, ref))
        return {k: visit(v, root, stack) for k, v in node.items()
                if not (profile == "inline_refs" and k == "$defs")}

    result = copy.deepcopy(definitions)
    for tool in result:
        schema = tool["function"]["parameters"]
        tool["function"]["parameters"] = visit(schema, schema)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("raw", "no_defaults", "inline_refs"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--send-model", action="store_true")
    args = parser.parse_args(argv)
    if not args.send_model:
        parser.error("Explicit --send-model required")
    output = args.output.resolve()
    if output.is_relative_to(ROOT.parent):
        parser.error("Raw evidence must stay outside repository")
    schema = transform(tools(), args.profile)
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "给我推荐20分钟内的一人晚餐。"}]
    output.mkdir(parents=True, exist_ok=False)
    save(output / "probe.json", {"profile": args.profile, "schema": schema, "messages": messages,
        "prompt_version": PROMPT_VERSION, "system_sha256": fingerprint(SYSTEM),
        "tools_sha256": fingerprint(schema), "scope": "no_business_execution"})
    model = RecordedModel(ChatModel(Settings().model_copy(update={
        "agent_enabled": True, "model_tool_protocol": "native"})), output)
    result = {"profile": args.profile, "valid_target_call": False, "business_execution": False}
    try:
        message = model.complete(messages, schema)
        calls = message.get("tool_calls", [])
        if len(calls) == 1 and calls[0]["function"]["name"] == "recommend_meal":
            arguments = json.loads(calls[0]["function"]["arguments"])
            body = PlanningInput.model_validate(arguments)
            result["valid_target_call"] = body.max_minutes == 20 and body.servings == 1
    except (ModelCallError, ValidationError, ValueError, KeyError, TypeError) as exc:
        result["diagnostic"] = exc.metadata["diagnostic"] if isinstance(exc, ModelCallError) else "invalid_arguments"
    result["model_calls"] = model.records
    save(output / "report.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "model_calls"}))
    return 0 if result["valid_target_call"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
