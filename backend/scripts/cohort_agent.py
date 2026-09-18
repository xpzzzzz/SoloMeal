"""Offline preregistration and configuration audit; never starts evaluation runs."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

EVALUATION = Path(__file__).resolve().parents[2] / "evaluation"
REPOSITORY = EVALUATION.parent
VERSION = "solomeal-cohort-v4"
LEGACY_VERSION = "solomeal-cohort-v3"
SPLITS = ("debug", "holdout")
# Registered approval extensions stay limited to preview-then-execute scenarios of that split.
CONFIRMATION_SCENARIOS = {"debug": {"A010", "A011", "A012"}, "holdout": {"A030", "A031", "A033"}}
ATTEMPT_KEYS = (
    "commit", "source_sha256", "prompt_version", "tool_protocol", "max_completion_tokens",
    "model_timeout_seconds", "system_sha256", "tools_sha256", "confirmation_extension",
    "direct_prompt_version", "direct_system_sha256",
)
MODEL_KEYS = ("model", "transport", "transport_version", "temperature", "top_p", "enable_thinking")
DATA_KEYS = {"dataset_sha256": "scenarios-v1.json", "protocol_sha256": "protocol-v1.json",
             "oracle_amendments_sha256": "amendments-v1.1.json",
             "budget_amendments_sha256": "amendments-v1.2.json"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def validate_config(config, version=VERSION):
    if set(config) != {"attempt", "model"}:
        raise ValueError("Configuration requires attempt and model sections")
    attempt_keys = ATTEMPT_KEYS if version == VERSION else ATTEMPT_KEYS[:-2]
    for section, keys in (("attempt", attempt_keys), ("model", MODEL_KEYS)):
        if set(config[section]) != set(keys):
            raise ValueError("All configuration fields must be explicitly registered")
        for key, value in config[section].items():
            if key not in ("max_completion_tokens", "model_timeout_seconds"):
                if not isinstance(value, str) or not value:
                    raise ValueError("Configuration strings must be nonempty")
    attempt = config["attempt"]
    if (type(attempt["max_completion_tokens"]) is not int
            or not 1 <= attempt["max_completion_tokens"] <= 3000
            or type(attempt["model_timeout_seconds"]) is not int
            or attempt["model_timeout_seconds"] != 30
            or attempt["tool_protocol"] not in ("native", "json")
            or attempt["confirmation_extension"] not in ("none", "approve")):
        raise ValueError("Unsupported budget, timeout, protocol or confirmation extension")


def slots(directory, split):
    if split not in SPLITS:
        raise ValueError("Unsupported cohort split")
    protocol = read(EVALUATION / "protocol-v1.json")["agent"]
    cases = read(EVALUATION / "scenarios-v1.json")["scenarios"]
    # Only IDs are selected here; the executor loads the requested split's prompts.
    ids = [c["id"] for c in cases if c["track"] == "agent" and c["split"] == split]
    return [{"scenario": case, "mode": mode, "repetition": repeat,
             "directory": str(directory / f"{case}-{mode}-{repeat:02}")}
            for case in ids for mode in protocol["modes"]
            for repeat in range(1, protocol["repetitions_per_scenario_per_mode"] + 1)]


def register(config, directory, output, split):
    validate_config(config)
    directory = directory.resolve()
    rows = slots(directory, split)
    if output.exists() or directory.exists():
        raise FileExistsError("Preregister before creating the trial root")
    if directory.is_relative_to(REPOSITORY):
        raise ValueError("Trial root must be private and outside repository")
    save(output, {"version": VERSION, "split": split, "config": config,
                  "registered_at": datetime.now(timezone.utc).isoformat(),
                  "trial_root": str(directory), "trials": rows,
                  "data_sha256": {key: digest(EVALUATION / name) for key, name in DATA_KEYS.items()},
                  "p8_gate": "incomplete", "scope": "preregistration_not_execution_approval"})


def load_plan(manifest, expected_sha256):
    if digest(manifest) != expected_sha256:
        raise ValueError("Manifest hash differs from preregistration")
    plan = read(manifest)
    # v3 manifests predate the split field, and the only cohort registered before it was debug.
    split = plan.get("split", "debug")
    if plan["version"] not in (VERSION, LEGACY_VERSION) or split not in SPLITS:
        raise ValueError("Unsupported cohort version or split")
    plan["split"] = split
    validate_config(plan["config"], plan["version"])
    root = Path(plan["trial_root"])
    if not root.is_absolute() or root.resolve().is_relative_to(REPOSITORY):
        raise ValueError("Trial root must be private and outside repository")
    if plan["trials"] != slots(root, split):
        raise ValueError("Every planned slot must remain in its original order")
    hashes = {key: digest(EVALUATION / name) for key, name in DATA_KEYS.items()}
    if hashes != plan["data_sha256"]:
        raise ValueError("Dataset or protocol changed")
    return plan


def slot_confirmation(plan, slot):
    if slot["scenario"] in CONFIRMATION_SCENARIOS[plan["split"]] and slot["mode"] != "direct_model":
        return plan["config"]["attempt"]["confirmation_extension"]
    return "none"


def preflight(manifest, expected_sha256, directory, attempt, model):
    """Reject mismatches before creating evidence, a database or a paid request."""
    plan = load_plan(manifest, expected_sha256)
    directory = directory.resolve()
    slot = next((s for s in plan["trials"] if Path(s["directory"]) == directory), None)
    if slot is None:
        raise ValueError("Output is not a preregistered slot")
    if directory.exists():
        raise FileExistsError("A scheduled trial cannot be restarted or overwritten")
    expected = {**plan["config"]["attempt"], **plan["data_sha256"],
                "confirmation_extension": slot_confirmation(plan, slot),
                "scenario": slot["scenario"], "mode": slot["mode"], "repetitions": 1}
    for key, value in expected.items():
        if type(attempt.get(key)) is not type(value) or attempt.get(key) != value:
            raise ValueError("Runtime configuration differs: " + key)
    if model != plan["config"]["model"]:
        raise ValueError("Runtime model configuration differs")
    if datetime.fromisoformat(attempt["started_at"]) < datetime.fromisoformat(plan["registered_at"]):
        raise ValueError("Trial predates registration")
    return {"manifest_sha256": expected_sha256, "repetition": slot["repetition"]}


def audit(manifest, expected_sha256):
    plan = load_plan(manifest, expected_sha256)
    root = Path(plan["trial_root"])
    hashes = plan["data_sha256"]
    rows = []
    expected = {**plan["config"]["attempt"], **hashes, "repetitions": 1}
    for slot in plan["trials"]:
        directory = Path(slot["directory"])
        paths = sorted(directory.glob("*.json")) if directory.exists() else []
        errors = []
        state = "not_started"
        request_count = None
        if directory.exists():
            state = "incomplete"
            if not (directory / "attempt.json").is_file():
                errors.append("missing_attempt")
            else:
                try:
                    attempt = read(directory / "attempt.json")
                    if attempt.get("cohort") != {"manifest_sha256": expected_sha256,
                                                  "repetition": slot["repetition"]}:
                        errors.append("cohort_binding")
                    if datetime.fromisoformat(attempt["started_at"]) < datetime.fromisoformat(plan["registered_at"]):
                        errors.append("trial_predates_registration")
                    for key, value in {**expected, "scenario": slot["scenario"], "mode": slot["mode"],
                                       "confirmation_extension": slot_confirmation(plan, slot)}.items():
                        if key not in attempt or type(attempt[key]) is not type(value) or attempt[key] != value:
                            errors.append("attempt:" + key)
                    call_attempts = sorted(directory.glob("call-*-attempt.json"))
                    call_results = sorted(directory.glob("call-*-result.json"))
                    request_count = len(call_attempts)
                    if len(call_attempts) > 8:
                        errors.append("request_limit")
                    if slot["mode"] == "fixed_workflow" and (call_attempts or call_results):
                        errors.append("fixed_mode_model_calls")
                    metadata = []
                    for index, call in enumerate(call_attempts, 1):
                        if call.name != f"call-{index:02}-attempt.json":
                            errors.append("call_sequence")
                        result_path = directory / call.name.replace("-attempt", "-result")
                        if not result_path.exists():
                            errors.append("missing_call_result")
                            continue
                        meta = read(result_path)["metadata"]
                        metadata.append(meta)
                        if plan["version"] == VERSION and slot["mode"] == "direct_model":
                            from app.services.agent_model import fingerprint

                            input_path = directory / call.name.replace("-attempt", "-input")
                            if not input_path.is_file():
                                errors.append("missing_direct_input")
                            else:
                                payload = read(input_path)
                                messages = payload["messages"]
                                if (not messages or messages[0].get("role") != "system"
                                        or fingerprint(messages[0].get("content"))
                                        != expected["direct_system_sha256"]):
                                    errors.append("direct_system_prompt")
                                if payload["tools"] != []:
                                    errors.append("direct_tools_present")
                                reservation = read(call)
                                for key, value in (("messages_sha256", fingerprint(messages)),
                                                   ("tools_sha256", fingerprint(payload["tools"]))):
                                    if meta.get(key) != value or reservation.get(key) != value:
                                        errors.append("direct_input:" + key)
                                if meta.get("wire_messages_sha256") != fingerprint(messages):
                                    errors.append("direct_wire_messages")
                        model_expected = {**plan["config"]["model"],
                                          "max_completion_tokens": expected["max_completion_tokens"],
                                          "timeout_seconds": expected["model_timeout_seconds"]}
                        # Direct-model baseline has no tools and uses native text transport.
                        model_expected.update(tool_protocol=expected["tool_protocol"]
                                              if slot["mode"] == "agent_tools" else "native")
                        for key, value in model_expected.items():
                            if key not in meta or type(meta[key]) is not type(value) or meta[key] != value:
                                errors.append("model:" + key)
                    if len(call_results) != len(metadata):
                        errors.append("orphan_call_result")
                    report_path = directory / "report.json"
                    if report_path.exists():
                        report = read(report_path)
                        if report["scenario_id"] != slot["scenario"] or report["mode"] != slot["mode"]:
                            errors.append("report_identity")
                        if (report["model_calls"] != metadata
                                or report["actual_requests"] != sum(m["request_sent"] for m in metadata)):
                            errors.append("report_calls")
                        if slot["mode"] != "fixed_workflow" and not call_attempts:
                            errors.append("missing_model_calls")
                        state = "failed" if (report.get("objective_pass") is False
                            or report.get("business_unchanged") is False) else "awaiting_review"
                except (ValueError, KeyError, TypeError, AttributeError):
                    errors.append("malformed_evidence")
            if errors:
                state = "invalid_evidence"
        rows.append({**slot, "status": state, "configuration_errors": sorted(set(errors)),
                     "request_attempt_files": request_count,
                     "evidence_sha256": {path.name: digest(path) for path in paths}})
    known = {Path(slot["directory"]).name for slot in plan["trials"]}
    unexpected = sorted(p.name for p in root.iterdir() if p.name not in known) if root.exists() else []
    return {"version": plan["version"], "split": plan["split"], "manifest_sha256": digest(manifest),
            "trials": rows,
            "scheduled_trials": len(rows), "unexpected_entries": unexpected,
            "counts": {state: sum(row["status"] == state for row in rows)
                       for state in ("not_started", "incomplete", "failed", "awaiting_review", "invalid_evidence")},
            "p8_gate": "incomplete", "success_rate": None,
            "scope": "configuration_audit_not_task_scoring"}


def bind_review(manifest, expected_sha256, review_path):
    # Recompute rather than trusting an editable scores file.
    from scripts.review_agent import score_review

    result = audit(manifest, expected_sha256)
    review, scores = score_review(review_path)
    by_directory = {row["directory"]: row for row in result["trials"]}
    for item, score in zip(review["trials"], scores, strict=True):
        directory = str(Path(item["directory"]).resolve())
        if directory not in by_directory:
            raise ValueError("Review contains a trial outside this cohort")
        row = by_directory[directory]
        if row["status"] in ("not_started", "invalid_evidence"):
            raise ValueError("Review requires valid started cohort evidence")
        if any(row["evidence_sha256"].get(k) != v
               for k, v in score["evidence_sha256"].items()):
            raise ValueError("Review evidence differs from cohort audit")
        row["review"] = score
    result.update(review_sha256=digest(review_path),
                  reviewed_trials=len(scores), scope="cohort_bound_review_not_gate_aggregation")
    # Keep every slot, including interrupted, invalid and unreviewed trials.
    return result


def main(argv=None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("register", "audit", "review", "summarize"))
    parser.add_argument("--review", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--split", choices=SPLITS)
    parser.add_argument("--trial-root", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "register":
        if not args.config or not args.trial_root or args.manifest or not args.split:
            parser.error("register requires --config, --trial-root and --split")
        register(read(args.config), args.trial_root, args.output, args.split)
        print(digest(args.output))
    else:
        if not args.manifest or not args.manifest_sha256 or args.config or args.trial_root or args.split:
            parser.error("audit requires --manifest and --manifest-sha256 saved at registration")
        if args.command == "summarize":
            from scripts.cohort_metrics import summarize

            save(args.output, summarize(args.manifest, args.manifest_sha256, args.review))
        elif args.command == "review":
            if not args.review:
                parser.error("review requires --review")
            save(args.output, bind_review(args.manifest, args.manifest_sha256, args.review))
        else:
            save(args.output, audit(args.manifest, args.manifest_sha256))


if __name__ == "__main__":
    main()
