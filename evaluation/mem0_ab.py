"""Reproducible synthetic A/B check; never contacts Mem0 or any model."""
import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.memory import MemoryPreference  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def checked(response, status):
    if response.status_code != status:
        raise RuntimeError(f"fixture request failed: {response.status_code} {response.text}")
    return response.json()


class FakeProvider:
    def __init__(self, memories):
        self.memories = memories
        self.users = []

    def get_preferences(self, user_id):
        self.users.append(str(user_id))
        return self.memories


def run():
    # Isolated database only; never load credentials or any existing user data.
    with tempfile.TemporaryDirectory(prefix="solomeal-memory-ab-") as tmp:
        database = f"sqlite:///{(Path(tmp) / 'test.db').as_posix()}"
        os.environ["SOLOMEAL_DATABASE_URL"] = database
        os.environ["SOLOMEAL_MEM0_ENABLED"] = "false"
        config = Config(str(ROOT / "backend" / "alembic.ini"))
        command.upgrade(config, "head")
        app = create_app(Settings(_env_file=None, database_url=database,
                                  receipt_storage_dir=Path(tmp) / "uploads",
                                  mem0_enabled=False, agent_enabled=False))
        with TestClient(app) as client:
            credentials = {"username": "memory_ab_fixture", "password": "a-strong-test-password"}
            user = checked(client.post("/api/v1/auth/register", json=credentials), 201)
            token = checked(client.post("/api/v1/auth/login", json=credentials), 200)["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            checked(client.put("/api/v1/me/preferences", headers=headers, json={
                "equipment": ["pan"], "excluded_ingredients": ["allergen"]}), 200)

            ingredients = {}
            for name, amount in [("rice", "100"), ("pepper", "98"), ("allergen", "100")]:
                ingredients[name] = checked(client.post("/api/v1/ingredients", headers=headers,
                    json={"name": name, "unit": "g"}), 201)["id"]
                checked(client.post("/api/v1/inventory", headers={**headers,
                    "Idempotency-Key": f"stock-{name}"}, json={
                    "ingredient_id": ingredients[name], "quantity": amount, "unit": "g"}), 201)
            recipes = [
                ("ordinary-boil", "rice", "boil", 25),
                ("ordinary-steam", "rice", "steam", 25),
                ("ordinary-stew", "rice", "stew", 25),
                ("preferred-stir-fry", "pepper", "stir_fry", 15),
                ("forbidden-stir-fry", "allergen", "stir_fry", 15),
                ("too-slow-stir-fry", "rice", "stir_fry", 40),
            ]
            recipe_ids = {}
            for name, ingredient, method, minutes in recipes:
                recipe_ids[name] = checked(client.post("/api/v1/recipes", headers=headers, json={
                    "name": name, "servings": 1, "minutes": minutes, "equipment": ["pan"],
                    "steps": ["cook"], "source": "synthetic evaluation", "cooking_methods": [method],
                    "ingredients": [{"ingredient_id": ingredients[ingredient], "quantity": "100", "unit": "g"}],
                }), 201)["id"]
            body = {"max_minutes": 30}
            cases = [("cooking_method", "stir_fry"), ("ingredient", "pepper"), ("time", "20")]
            result_cases = []
            disabled_provider = client.app.state.memory_provider
            assert not disabled_provider.enabled
            for category, target in cases:
                # A uses the disabled provider. B contains one relevant and one unrelated
                # fake memory. No extraction or remote retrieval is claimed.
                pref = MemoryPreference(category=category, target=target, polarity=1)
                unrelated = MemoryPreference(category="ingredient", target="unrelated-food", polarity=1)
                groups = {}
                for group, provider in [("A", disabled_provider), ("B", FakeProvider([pref, unrelated]))]:
                    timings = []
                    responses = []
                    client.app.state.memory_provider = provider
                    for _ in range(10):
                        start = time.perf_counter()
                        response = checked(client.post("/api/v1/recommendations", headers=headers, json=body), 200)
                        timings.append((time.perf_counter() - start) * 1000)
                        responses.append(response)
                    if any(response != responses[0] for response in responses):
                        raise RuntimeError("unstable recommendation results during repeat")
                    response = responses[0]
                    top = response["candidates"][:3]
                    rejected = {item["recipe_id"]: item["reasons"] for item in response["rejected"]}
                    assert rejected[recipe_ids["forbidden-stir-fry"]] == ["EXCLUDED_INGREDIENT"]
                    assert rejected[recipe_ids["too-slow-stir-fry"]] == ["TIME_LIMIT"]
                    if group == "B":
                        assert len(provider.users) == 10
                        assert all(uid == str(user["id"]) for uid in provider.users)
                    for candidate in response["candidates"]:
                        reasons = (candidate.get("memory_preference") or {}).get("reasons", [])
                        assert all(reason["target"] != "unrelated-food" for reason in reasons)
                    groups[group] = {
                        "top3": [{"name": c["recipe"]["name"], "base_score": c["base_score"], "score": c["score"],
                                  "memory_preference": c.get("memory_preference")} for c in top],
                        "preferred_in_top3": sum(c["recipe"]["name"] == "preferred-stir-fry" for c in top),
                        "hard_constraints_passed": 2,
                        "hard_constraints_total": 2,
                        "median_request_ms": round(statistics.median(timings), 3),
                    }
                assert groups["A"]["preferred_in_top3"] == 0
                assert groups["B"]["preferred_in_top3"] == 1
                preferred = groups["B"]["top3"][0]
                assert preferred["name"] == "preferred-stir-fry"
                assert preferred["base_score"] == 58.8
                assert preferred["score"] == 61.8
                assert preferred["memory_preference"]["points"] == 3
                assert preferred["memory_preference"]["reasons"][0]["target"] == target
                groups["additional_median_ms"] = round(groups["B"]["median_request_ms"] - groups["A"]["median_request_ms"], 3)
                result_cases.append({"preference": {"category": category, "target": target, "polarity": 1},
                    "fake_returned_relevant": 1, "fake_returned_unrelated": 1, "groups": groups})
            return {"kind": "synthetic engineering comparison, not real retrieval or quality evaluation",
                    "request": body, "repeats_per_group": 10, "cases": result_cases,
                    "real_mem0_latency_ms": None, "real_model_tokens": None, "real_service_cost": None,
                    "notes": ["A uses the disabled provider; B uses a fake provider.",
                              "Both groups use the same user, database, recipes, constraints and request.",
                              "Elapsed time includes local HTTP handling; fake overhead is not service latency.",
                              "Fake retrieval returns prescribed records and cannot establish actual retrieval accuracy."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True, help="new JSON report path")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new path")
    report = run()
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(f"Saved synthetic comparison to {args.output}")
