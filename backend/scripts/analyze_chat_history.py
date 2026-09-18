"""Offline allowlisted latency summary; historical mixes are not evaluation cohorts."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean


def analyze(root):
    rows = []
    for directory in sorted(root.glob("p8-*")):
        for path in sorted(directory.glob("call-*-result.json")):
            body = json.loads(path.read_text(encoding="utf-8"))
            metadata = body.get("metadata", {})
            if metadata.get("request_sent") is not True:
                continue
            message = body.get("message") or {}
            usage = metadata.get("usage") or {}
            rows.append({"source": f"{directory.name}/{path.name}",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "phase": "first" if path.name == "call-01-result.json" else "later",
                "output_kind": "tool" if message.get("tool_calls") else
                               "final" if message.get("content") else "missing",
                **{k: metadata.get(k) for k in ("diagnostic", "elapsed_seconds", "model",
                    "protocol_version", "max_completion_tokens", "wire_messages_sha256")},
                **{k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens")}})
    groups = {}
    for phase in ("first", "later"):
        selected = [r for r in rows if r["phase"] == phase]
        known = [r for r in selected if r["prompt_tokens"] is not None]
        groups[phase] = {"count": len(selected), "usage_known": len(known),
            "diagnostics": dict(Counter(r["diagnostic"] or "response" for r in selected)),
            "mean_elapsed_seconds": mean(r["elapsed_seconds"] for r in selected) if selected else None,
            "observed_prompt_range": [min(r["prompt_tokens"] for r in known),
                                      max(r["prompt_tokens"] for r in known)] if known else None}
    return {"version": "chat-history-v1", "scope": "top_level_p8_call_results_only",
            "not_cumulative_usage_ledger": True, "not_comparable_cohort": True,
            "later_is_not_always_final": True, "groups": groups, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.source)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(result["groups"]))


if __name__ == "__main__":
    main()
