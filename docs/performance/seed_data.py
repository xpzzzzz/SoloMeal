"""Fixed-seed synthetic read workload. Refuses an occupied performance database."""
import argparse
import hashlib
import json
import random
import secrets
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select

from app.core.config import Settings
from app.core.database import build_engine, build_session_factory
from app.models.food import CookingRecord, Ingredient, IngredientAlias, InventoryBatch
from app.models.food import Recipe, RecipeFeedback, RecipeIngredient
from app.models.identity import AuthSession, User, UserPreference
from app.models.shopping import SavedQuote, ShoppingList
from app.services.identity import digest_token, password_hasher
from sandbox import require_models_off, require_sandbox


def ident(seed, label):
    return str(uuid5(NAMESPACE_URL, f"solomeal-perf/{seed}/{label}"))


def seed_data(seed, as_of, users_per_scale, credentials, manifest):
    settings = Settings(_env_file=None)
    require_sandbox(settings.database_url)
    require_models_off(settings)
    if credentials.exists() or manifest.exists():
        raise RuntimeError("Refusing to overwrite credentials or fixture manifest")
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    records, counts = [], {}
    fingerprint = hashlib.sha256()
    # This is a reproducible data seed, not a production account generator.
    password_hash = password_hasher.hash(secrets.token_urlsafe(24))
    with factory() as db:
        if db.scalar(select(func.count()).select_from(User)):
            raise RuntimeError("Performance database must be empty; use a new project")
        for scale in (10, 100, 500):
            counts[str(scale)] = {"users": users_per_scale, "recipes_per_user": scale,
                                  "ingredients_per_user": 64,
                                  "batches_per_user": scale * 4,
                                  "history_per_user": max(40, min(scale * 2, 400)),
                                  "shopping_per_user": max(3, scale // 10)}
            for user_no in range(users_per_scale):
                label = f"r{scale}/u{user_no}"
                rng = random.Random(f"{seed}/{label}")
                uid = ident(seed, label)
                db.add(User(id=uid, username=f"perf-{scale}-{user_no}", password_hash=password_hash))
                db.flush()
                db.add(UserPreference(user_id=uid, equipment=["煮锅", "平底锅"],
                                      excluded_ingredients=[], default_servings=1, max_minutes=60,
                                      personal_time_enabled=True, personalization_enabled=True))
                token = secrets.token_urlsafe(32)
                db.add(AuthSession(token_hash=digest_token(token), user_id=uid,
                                   expires_at=int(time.time()) + 7 * 86400))
                records.append({"scale": scale, "user_id": uid, "token": token})
                ingredients = []
                for n in range(64):
                    iid = ident(seed, f"{label}/i{n}")
                    unit = ("g", "ml", "piece")[n % 3]
                    ingredient = {"id": iid, "name": f"测试食材{n:03d}", "unit": unit,
                                  "is_staple": n == 0}
                    ingredients.append(ingredient)
                    db.add(Ingredient(user_id=uid, **ingredient))
                db.flush()
                for n, item in enumerate(ingredients):
                    db.add(IngredientAlias(id=ident(seed, f"{label}/a{n}"), user_id=uid,
                                           ingredient_id=item["id"], alias=f"测试别名{n:03d}"))
                    if n < 16:
                        db.add(SavedQuote(id=ident(seed, f"{label}/q{n}"), user_id=uid,
                                          ingredient_id=item["id"], package_quantity=Decimal(10),
                                          package_price=Decimal("8.00"), currency="CNY",
                                          source="synthetic benchmark", observed_on=as_of, version=1))
                for n in range(scale * 4):
                    item = ingredients[n % 64]
                    row = dict(id=ident(seed, f"{label}/b{n}"), user_id=uid,
                               ingredient_id=item["id"], quantity=Decimal(1000 + rng.randrange(500)),
                               expires_on=as_of + timedelta(days=(-1, 2, 10, 30)[n % 4]),
                               expiry_source="user", location="fridge", version=1,
                               archived=n % 17 == 0,
                               created_at=datetime.combine(as_of, datetime.min.time()) - timedelta(minutes=n))
                    fingerprint.update(json.dumps(row, sort_keys=True, default=str).encode())
                    db.add(InventoryBatch(**row))
                snapshots = []
                for n in range(scale):
                    rid = ident(seed, f"{label}/r{n}")
                    recipe = dict(id=rid, user_id=uid, name=f"测试菜谱{n:04d}", servings=1,
                                  minutes=10 + n % 20, equipment=["煮锅"], steps=["合成测量步骤"],
                                  source="synthetic benchmark", version=1, source_type="manual",
                                  source_ref=None, cooking_methods=[])
                    fingerprint.update(json.dumps(recipe, sort_keys=True).encode())
                    db.add(Recipe(**recipe))
                    chosen = rng.sample(ingredients, 5)
                    snapshot = {k: v for k, v in recipe.items() if k != "user_id"}
                    snapshot["ingredients"] = []
                    snapshots.append(snapshot)
                    db.flush()
                    for j, item in enumerate(chosen):
                        quantity = Decimal(1 if item["unit"] == "piece" else 50)
                        db.add(RecipeIngredient(id=ident(seed, f"{label}/r{n}/line{j}"), user_id=uid,
                                                recipe_id=rid, ingredient_id=item["id"],
                                                quantity=quantity, optional=j == 4))
                        snapshot["ingredients"].append({"ingredient_id": item["id"],
                                                       "name": item["name"], "unit": item["unit"],
                                                       "quantity": str(quantity), "optional": j == 4,
                                                       "is_staple": item["is_staple"]})
                    if n % 3 == 0:
                        db.add(RecipeFeedback(id=ident(seed, f"{label}/feedback{n}"), user_id=uid,
                                              recipe_id=rid, favorite=n % 2 == 0, rating="like",
                                              version=1, updated_at=datetime.combine(as_of, datetime.min.time())))
                for n in range(counts[str(scale)]["history_per_user"]):
                    # Read-side synthetic historical snapshots; not an undo/cooking fixture.
                    snapshot = snapshots[n % scale]
                    db.add(CookingRecord(id=ident(seed, f"{label}/h{n}"), user_id=uid,
                                         recipe_snapshot=snapshot, servings=1,
                                         actual_minutes=10 + n % 20, duration_source="manual",
                                         feedback_version=1, status="completed",
                                         created_at=datetime.combine(as_of, datetime.min.time())
                                         - timedelta(days=1 + n % 80, minutes=n)))
                for n in range(counts[str(scale)]["shopping_per_user"]):
                    items = [{"ingredient_id": item["id"], "name": item["name"],
                              "unit": item["unit"], "quantity": "10"} for item in ingredients[n % 30:n % 30 + 3]]
                    db.add(ShoppingList(id=ident(seed, f"{label}/shopping{n}"), user_id=uid,
                                        origin={"kind": "single_plan", "recipe_name": "合成采购"},
                                        items=items, checked_ingredient_ids=[], result={}, status="draft",
                                        created_at=datetime.combine(as_of, datetime.min.time()) - timedelta(minutes=n)))
        db.commit()
    engine.dispose()
    credentials.parent.mkdir(parents=True, exist_ok=True)
    with credentials.open("x", encoding="utf-8") as out:
        json.dump(records, out)
    fixture = {"seed": seed, "as_of": str(as_of), "scales": counts,
               "data_fingerprint_recipe_and_inventory": fingerprint.hexdigest(),
               "users": [{k: v for k, v in row.items() if k != "token"} for row in records],
               "note": "Synthetic read-side fixture; credentials excluded; no real user data"}
    with manifest.open("x", encoding="utf-8") as out:
        json.dump(fixture, out, ensure_ascii=False, indent=2)
    print(json.dumps({"seed": seed, "scales": counts, "manifest": manifest.name}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1014)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--users-per-scale", type=int, default=5, choices=range(1, 11))
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    seed_data(args.seed, args.as_of, args.users_per_scale, args.credentials, args.manifest)
