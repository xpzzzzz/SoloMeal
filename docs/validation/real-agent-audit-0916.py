"""Offline audit: bind request inputs, outcomes and UI checkpoints without reruns."""
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.agent_model import fingerprint
from app.services.tool_protocol import wire_messages
from scripts.diagnose_purchase import source_hash


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


base = Path("D:/SoloMeal-Acceptance")
first = base / "p8-real-agent-0916-01"
page = base / "p6-real-ui-0916-01"
second = base / "p8-real-multi-0916-02"
out = base / "real-agent-audit-0916-01"
out.mkdir(exist_ok=False)

# Reconstruct and verify the exact original driver after a sandbox-denied archive copy.
driver = ROOT / "docs/validation/real-agent-0916.py"
v1 = driver.read_text(encoding="utf-8").replace('"real-agent-diagnostic-0916-v2"', '"real-agent-diagnostic-0916-v1"')
v1 = v1.replace('def diagnostic(folder, settings, slots=("multi", "recovery")):\n    for name in slots:',
                'def diagnostic(folder, settings):\n    for name in ("multi", "recovery"):')
start = v1.index('                reread = ')
end = v1.index('                writes = ', start)
v1 = v1[:start] + '                immutable = all(request(client, "GET", f"agent/runs/{r[\'id\']}", headers) == r for r in runs[:-1])\n' + v1[end:]
v1 = v1.replace('choices=("diagnostic", "multi", "serve")', 'choices=("diagnostic", "serve")')
v1 = v1.replace('if args.mode in ("diagnostic", "multi"):\n        diagnostic(args.output, settings, ("multi",) if args.mode == "multi" else ("multi", "recovery"))',
                'if args.mode == "diagnostic":\n        diagnostic(args.output, settings)')
assert hashlib.sha256(v1.encode()).hexdigest() == read(first / "registration.json")["driver_sha256"]
with (ROOT / "docs/validation/real-agent-0916-v1.py").open("xb") as stream:
    stream.write(v1.encode())

calls, registrations = [], []
for batch in (first, page, second):
    registration = read(batch / "registration.json")
    assert registration["source_sha256"] == source_hash()
    assert fingerprint(registration["protocol"]) == registration["protocol_sha256"]
    for name, expected in registration["frozen_json"].items():
        assert sha(ROOT / "evaluation" / name) == expected
    for path in sorted(batch.rglob("call-*-input.json")):
        value = read(path)
        attempt = read(path.with_name(path.name.replace("input", "attempt")))
        metadata = read(path.with_name(path.name.replace("input", "result")))["metadata"]
        assert fingerprint(value["messages"]) == attempt["messages_sha256"] == metadata["messages_sha256"]
        assert fingerprint(value["tools"]) == attempt["tools_sha256"] == metadata["tools_sha256"]
        assert fingerprint(wire_messages(value["messages"], value["tools"])) == metadata["wire_messages_sha256"]
        assert metadata["http_status"] == 200 and metadata["diagnostic"] is None
        assert metadata["timeout_seconds"] == 30 and metadata["max_completion_tokens"] == 3000
        assert metadata["enable_thinking"] == "false" and metadata["tool_protocol"] == "json"
        calls.append({"batch": batch.name, "file": str(path.relative_to(batch)), **metadata})
    registrations.append({"batch": batch.name, "registration_sha256": sha(batch / "registration.json")})

states = {name: read(page / (name + ".json")) for name in (
    "inventory-preview", "inventory-restored", "inventory-approved", "cooking-preview",
    "cooking-approved", "undo-preview", "undo-approved")}
def rice(state):
    return sum(Decimal(b["quantity"]) for b in state["inventory"] if b["name"] == "大米")

assert [rice(s) for s in states.values()] == list(map(Decimal, (300, 300, 400, 400, 320, 320, 400)))
assert states["inventory-preview"]["runs"] == states["inventory-restored"]["runs"]
for previous, preview in (("inventory-approved", "cooking-preview"), ("cooking-approved", "undo-preview")):
    for resource in ("inventory", "inventory/events", "cooking", "plans", "recipes", "quotes"):
        assert states[previous][resource] == states[preview][resource]
final = states["undo-approved"]
assert len(final["runs"]) == 3 and all(r["status"] == "approved" for r in final["runs"])
assert len(final["cooking"]) == 1 and final["cooking"][0]["status"] == "retracted"
events = final["inventory/events"]
consume = next(e for e in events if e["reason"] == "cooking")
undo = next(e for e in events if e["reason"] == "undo")
assert consume["batch_id"] == undo["batch_id"] and Decimal(consume["delta"]) == -80 and Decimal(undo["delta"]) == 80
assert len(events) == 5
assert read(first / "multi/report.json")["objective_pass"] is False
assert read(first / "recovery/report.json")["objective_pass"] is True
assert read(second / "multi/report.json")["objective_pass"] is True

review = {
    "reviewer": "Codex", "human_clarity": None, "registrations": registrations,
    "first_multi": {"objective_pass": False, "semantic_pass": True,
                    "limitation": "Driver compared live session navigation metadata; original failure retained; no final parent reread retained."},
    "recovery": {"objective_pass": True, "semantic_pass": True,
                 "limitation": "Controlled invalid call; real model recovery only. Answer includes extra menu options but correct requested rice purchase, source and date."},
    "second_multi": {"objective_pass": True, "semantic_pass": False,
                     "reason": "Turn 3 offers cooking preview although one egg is missing; same answer also requires replenishment, leaving a contradictory next step. Preserve failure."},
    "page": {"business_pass": True, "refresh_pending_same_run": True,
             "rice_checkpoints": [str(rice(s)) for s in states.values()],
             "display_defect": "Internal history JSON shown; subsequently fixed and tested with scripted model, no further real calls.",
             "shutdown": "Process interrupted exit 1, final checkpoint saved before shutdown; no finally after.json/runs.json produced."},
    "actual_requests": len(calls),
    "usage": {key: sum(c["usage"][key] for c in calls) for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
    "model_elapsed_seconds_sum": sum(c["elapsed_seconds"] for c in calls),
    "cumulative_chat": 1635 + len(calls), "cumulative_vision": 30,
    "source_sha256": source_hash(), "holdout_gate": "unchanged_failed", "holdout_score": "48/60",
    "evidence_hashes": {str(p.relative_to(base)): sha(p) for b in (first, page, second) for p in b.rglob("*.json")},
}
save(out / "audit.json", review)
save(out / "calls.json", calls)
save(ROOT / "docs/validation/real-agent-0916.json", {k: v for k, v in review.items() if k != "evidence_hashes"})
print(json.dumps({k: review[k] for k in ("actual_requests", "usage", "cumulative_chat", "model_elapsed_seconds_sum")}, indent=2))
