"""Offline evidence audit for the completed, non-repeatable four-turn diagnostic."""

import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.agent import SYSTEM, tools
from app.services.agent_model import fingerprint
from app.services.tool_protocol import wire_messages
from scripts.diagnose_purchase import source_hash
from scripts.evaluate_agent import save
from scripts.recommendation_diagnostic import PROTOCOL, check_turn, digest

FOLDER = Path("D:/SoloMeal-Acceptance/p8-recommendation-response-0916-01")
OUTPUT = Path("D:/SoloMeal-Acceptance/p8-recommendation-response-audit-0916-01")


def read(name):
    return json.loads((FOLDER / name).read_text(encoding="utf-8"))


def main():
    registration, report, completion = (read(n) for n in ("registration.json", "report.json", "completion.json"))
    assert registration["source_sha256"] == completion["source_sha256"] == source_hash()
    assert registration["protocol_sha256"] == fingerprint(PROTOCOL)
    assert registration["driver_sha256"] == digest(ROOT / "backend/scripts/recommendation_diagnostic.py")
    assert registration["system_sha256"] == fingerprint(SYSTEM)
    assert registration["tools_sha256"] == fingerprint(tools())
    for name, value in registration["files"].items():
        assert digest(ROOT / name) == value, name
    totals = {key: 0 for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    finals, calls = [], []
    for path in sorted(FOLDER.glob("call-*-result.json")):
        result = read(path.name)
        stem = path.name.removesuffix("-result.json")
        inputs, attempt = read(stem + "-input.json"), read(stem + "-attempt.json")
        meta = result["metadata"]
        assert fingerprint(inputs["messages"]) == meta["messages_sha256"] == attempt["messages_sha256"]
        assert fingerprint(inputs["tools"]) == meta["tools_sha256"] == attempt["tools_sha256"]
        assert fingerprint(wire_messages(inputs["messages"], inputs["tools"])) == meta["wire_messages_sha256"]
        assert meta["http_status"] == 200 and meta["diagnostic"] is None
        assert meta["timeout_seconds"] == 30 and meta["max_completion_tokens"] == 3000
        assert meta["model"] == registration["model"] and meta["enable_thinking"] == "false"
        assert meta["tool_protocol"] == "json" and meta["protocol_version"] == "json-tools-v2"
        for key in totals:
            totals[key] += meta["usage"][key]
        calls.append(meta)
        if not result["message"].get("tool_calls"):
            finals.append(result["message"]["content"])
    assert len(calls) == report["requests"] == len(list(FOLDER.glob("call-*-attempt.json"))) <= 32
    assert len(finals) == 4
    reviews = []
    notes = [
        "1人/25分钟、80克大米及1蛋与工具一致；两道库存均足够，邀请选择预览未声称已创建。",
        "3人/25分钟、240克大米及3蛋正确；仅建议白米饭预览，蛋炒饭明确先采购入库。未明说缺1蛋为表达省略，未给错误缺口。",
        "3人/15分钟、240克大米/3蛋及缺1蛋正确；明确不能当前预览，先入库后重新查询。",
        "补入1蛋后重新查询，3人/15分钟、240克大米/3蛋正确；库存足够才建议请求预览，未宣称已执行。",
    ]
    for index in range(4):
        evidence = read(f"turn-{index + 1}.json")
        run = evidence["run"]
        assert check_turn(run, index) and evidence["before"] == evidence["after"]
        assert run["result"]["model_message"] == finals[index]
        reviews.append({"turn": index + 1, "evidence_sha256": digest(FOLDER / f"turn-{index + 1}.json"),
            "model_message_sha256": fingerprint(finals[index]),
            "product_message_sha256": fingerprint(run["result"]["message"]),
            "model_semantic_pass": True, "model_reason": notes[index],
            "product_semantic_pass": True,
            "product_reason": "展示条件、用量、缺口及逐菜后续步骤与本轮工具一致；未创建确认项的状态说明正确。",
            "human_clarity": None})
    mutation = read("driver-stock-in.json")
    before, after = mutation["before"], mutation["after"]
    def total(state, name):
        return sum(Decimal(row["quantity"]) for row in state["inventory"] if row["name"] == name)
    assert total(before, "鸡蛋") == 2 and total(after, "鸡蛋") == 3
    assert total(before, "大米") == total(after, "大米") == 300
    for key in ("cooking", "plans", "recipes", "quotes"):
        assert before[key] == after[key]
    assert len(after["inventory/events"]) == len(before["inventory/events"]) + 1
    assert report["objective_pass"] and report["runs_unchanged"]
    assert report["writes"]["count"] == report["writes"]["attempted_statements"] == 0
    assert report["writes"]["complete"]
    reread = read("reread.json")
    for index, restored in enumerate(reread):
        old = read(f"turn-{index + 1}.json")["run"]
        assert all(old[k] == restored[k] for k in old if k not in ("session_version", "latest_run_id"))
    audit = {"batch": FOLDER.name, "reviewer": "Codex", "scope": "exposed_regression_not_holdout",
        "source_sha256": source_hash(), "requests": len(calls), "usage": totals,
        "model_elapsed_seconds": sum(c["elapsed_seconds"] for c in calls),
        "wall_seconds": (datetime.fromisoformat(completion["completed_at"]) -
                         datetime.fromisoformat(registration["started_at"])).total_seconds(),
        "all_input_hashes_match": True, "objective_pass": True, "reviews": reviews,
        "model_semantic_passes": 4, "product_semantic_passes": 4, "human_clarity": None,
        "known_chat_requests": 1655 + len(calls), "vision_requests": 30,
        "unauthorized_business_DML": 0, "driver_write": "one synthetic egg via explicit API, not model/UI",
        "limitation": "Later model turns see deterministic product answers in history; not a pure model or blind comparison.",
        "files": {p.name: digest(p) for p in sorted(FOLDER.glob("*.json"))}}
    OUTPUT.mkdir(exist_ok=False)
    save(OUTPUT / "audit-review.json", audit)
    save(ROOT / "docs/validation/recommendation-diagnostic-0916.json", audit)
    print(json.dumps({k: v for k, v in audit.items() if k not in ("reviews", "files")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
