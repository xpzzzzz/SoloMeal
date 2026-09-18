"""One A014 v8 final-request budget probe; no retries or business execution."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.services.agent_model import fingerprint
from scripts.evaluate_agent import save
from scripts.probe_a014_timeout import reconstructed, request

VERSION = "a014-final-budget-v1"


def verify_baseline(settings, wire, baseline):
    attempt = json.loads((baseline / "replay-attempt.json").read_text(encoding="utf-8"))
    payload = {"model": settings.model_name, "messages": wire,
               "max_completion_tokens": 1500, "response_format": {"type": "json_object"}}
    if (attempt["payload_sha256"] != fingerprint(payload)
            or attempt["timeout_seconds"] != 60
            or attempt["max_completion_tokens"] != 1500
            or attempt["enable_thinking"] != "not_sent"):
        raise ValueError("Baseline differs; no request allowed")


def run(settings, wire, directory, *, transport=None):
    result = request(settings, wire, 60, directory, "replay", transport=transport,
                     max_completion_tokens=3000)
    save(directory / "report.json", {"version": VERSION, "results": [result],
         "actual_requests": 1, "maximum_requests": 1, "business_execution": False,
         "within_production_timeout": result["elapsed_seconds"] <= 30,
         "p8_gate": "incomplete", "cost": None})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--send-model", action="store_true")
    args = parser.parse_args(argv)
    if not args.send_model or args.output.resolve().is_relative_to(ROOT.parent):
        parser.error("Explicit --send-model and private output outside repository required")
    wire, old = reconstructed(args.source)
    settings = Settings()
    if settings.model_name != old["model"]:
        parser.error("Model must match original")
    verify_baseline(settings, wire, args.baseline)
    args.output.mkdir(parents=True, exist_ok=False)
    paths = {"source_report": args.source / "report.json",
             "baseline_attempt": args.baseline / "replay-attempt.json",
             "script": Path(__file__), "reconstruction_transport": Path(__file__).with_name("probe_a014_timeout.py")}
    save(args.output / "probe.json", {"version": VERSION, "source": str(args.source),
         "baseline": str(args.baseline), "original_metadata": old,
         "files_sha256": {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()},
         "three_input_hashes_verified": True, "baseline_payload_verified": True,
         "maximum_requests": 1, "scope": "no_business_execution"})
    result = run(settings, wire, args.output)
    print(json.dumps({k: result[k] for k in ("valid_final", "diagnostic", "elapsed_seconds", "usage")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
