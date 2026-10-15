"""Verify synthetic row counts and fingerprint read-side data before/after load."""
import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from app.core.config import Settings
from app.core.database import build_engine
from sandbox import require_models_off, require_sandbox

TABLES = ("users", "user_preferences", "auth_sessions", "ingredients", "ingredient_aliases",
          "recipes", "recipe_ingredients", "recipe_feedback", "inventory_batches", "cooking_records",
          "price_quotes", "shopping_lists", "operations", "inventory_events", "receipt_imports")


def checkpoint(directory, name):
    settings = Settings(_env_file=None)
    require_sandbox(settings.database_url)
    require_models_off(settings)
    fixture = json.loads((directory / "fixture.json").read_text())
    engine = build_engine(settings.database_url)
    hashes, counts = {}, {}
    with engine.connect() as db:
        for table in TABLES:
            rows = [dict(r) for r in db.execute(text("SELECT * FROM " + table)).mappings()]
            for row in rows:
                for key in ("password_hash", "token_hash", "expires_at"):
                    row.pop(key, None)
            rows.sort(key=lambda r: json.dumps(r, sort_keys=True, default=str))
            hashes[table] = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
            counts[table] = len(rows)
        for scale, parameters in fixture["scales"].items():
            for owner in [r for r in fixture["users"] if str(r["scale"]) == scale]:
                for table, count_key in (("recipes", "recipes_per_user"), ("inventory_batches", "batches_per_user"),
                                         ("cooking_records", "history_per_user"), ("shopping_lists", "shopping_per_user")):
                    actual = db.execute(text("SELECT COUNT(*) FROM " + table + " WHERE user_id=:owner"),
                                        {"owner": owner["user_id"]}).scalar_one()
                    if actual != parameters[count_key]:
                        raise RuntimeError("Fixture row count mismatch: " + table)
    engine.dispose()
    data = {"table_counts": counts, "table_semantic_hashes": hashes,
            "secret_fields_excluded": ["password_hash", "token_hash", "expires_at"]}
    before = directory / "checkpoint-before.json"
    if name == "after":
        prior = json.loads(before.read_text())
        data["unchanged"] = prior["table_semantic_hashes"] == hashes and prior["table_counts"] == counts
        if not data["unchanged"]:
            raise RuntimeError("Load workload changed the seeded database")
    with (directory / ("checkpoint-" + name + ".json")).open("x", encoding="utf-8") as out:
        json.dump(data, out, indent=2)
    print(json.dumps({"checkpoint": name, "table_counts": counts, "unchanged": data.get("unchanged")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path("/perf-output"))
    parser.add_argument("--name", choices=("before", "after"), required=True)
    args = parser.parse_args()
    checkpoint(args.directory, args.name)
