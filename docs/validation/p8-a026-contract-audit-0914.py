"""Offline A026 contract reproduction; stdout is JSON, no model client is created."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings
from app.models.food import Ingredient
from app.schemas.agent import PurchaseEstimateInput
from app.services.planning import estimate_purchase
from scripts.diagnose_purchase import source_hash
from scripts.evaluate_agent import (
    holdout_planning_check,
    isolated_client,
    request,
    seed,
    shopping_line,
    snapshot,
)


def main():
    frozen = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((ROOT / "evaluation").glob("*.json"))}
    original_source = source_hash()
    rows = []
    with isolated_client(Settings(_env_file=None, agent_enabled=False)) as client:
        headers = seed(client, "low_stock_quoted")
        before = snapshot(client, headers)
        for arguments in ({"budget": "6"}, {"servings": 3, "budget": "6"}):
            result = request(client, "POST", "recommendations", headers, arguments)
            rice = shopping_line(next(c for c in result["candidates"]
                                     if c["recipe"]["name"] == "白米饭"), "大米")
            rows.append({"arguments": arguments, "servings": result["constraints"]["servings"],
                         "rice": rice, "legacy_oracle_pass": holdout_planning_check("A026", result)})
        quote = before["quotes"][0]
        with client.app.state.sessions() as db:
            ingredient = db.get(Ingredient, quote["ingredient_id"])
            estimate = estimate_purchase(db, ingredient.user_id, PurchaseEstimateInput(
                ingredient_id=ingredient.id, quantity="190", unit="g", budget="6"))
        unchanged = before == snapshot(client, headers)
    assert [r["servings"] for r in rows] == [1, 3]
    assert [r["legacy_oracle_pass"] for r in rows] == [False, True]
    assert [r["rice"]["packages"] for r in rows] == [1, 2]
    assert estimate["packages"] == 2 and estimate["estimated_cost"] == "6.00"
    assert estimate["source"] == quote["source"] and estimate["observed_on"] == quote["observed_on"]
    assert unchanged and original_source == source_hash()
    assert frozen == {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted((ROOT / "evaluation").glob("*.json"))}
    # Generated IDs are irrelevant to the public contract evidence.
    for row in rows:
        row["rice"].pop("ingredient_id", None)
    estimate["ingredient"].pop("id", None)
    print(json.dumps({"version": "a026-contract-audit-v1", "model_requests": 0,
                      "source_sha256": original_source, "frozen_json_sha256": frozen,
                      "recommendations": rows, "estimate_purchase": estimate,
                      "business_unchanged": unchanged}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
