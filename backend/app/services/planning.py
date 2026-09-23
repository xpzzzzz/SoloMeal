"""Read-only single-meal planner. Estimates never reserve or mutate inventory."""

from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import select

from ..models.food import CookingRecord, Ingredient, IngredientAlias, InventoryBatch, Recipe
from ..models.identity import UserPreference
from ..models.shopping import SavedQuote
from ..schemas.planning import PriceQuote, ScoreWeights
from .food import convert, feedback_map, normalize, owned, recipe_view
from .personal_time import duration_samples, estimate
from .personalization import history as preference_history
from .personalization import score_candidate
from .quantities import required_quantities, selected_lines


def freeze_quotes(db, user_id, body):
    quotes = {}
    if body.use_saved_quotes:
        for row in db.scalars(select(SavedQuote).where(SavedQuote.user_id == user_id)):
            quotes[row.ingredient_id] = PriceQuote(
                ingredient_id=row.ingredient_id, package_quantity=row.package_quantity,
                package_price=row.package_price, source=row.source, observed_on=row.observed_on)
    for quote in body.quotes:
        quotes[str(quote.ingredient_id)] = quote
    return body.model_copy(update={"quotes": [quotes[k] for k in sorted(quotes)], "use_saved_quotes": False})


def quote_snapshot(body, recipe):
    ids = {line["ingredient_id"] for line in recipe["ingredients"]}
    return body.model_copy(update={"quotes": [q for q in body.quotes if str(q.ingredient_id) in ids]})


def purchase_fields(needed, quote, today):
    """Whole packages a shortage costs, priced only from a quote the server already holds."""
    fields = {"packages": None, "purchase_quantity": None, "estimated_cost": None,
              "source": None, "observed_on": None, "price_status": "unknown"}
    if quote is None:
        return fields, Decimal(0)
    fields.update(source=quote.source, observed_on=quote.observed_on.isoformat())
    if (today - quote.observed_on).days > 30:
        fields["price_status"] = "stale"
        return fields, Decimal(0)
    packages = int((needed / quote.package_quantity).to_integral_value(rounding=ROUND_CEILING))
    subtotal = quote.package_price * packages
    fields.update(packages=packages, purchase_quantity=str(quote.package_quantity * packages),
                  estimated_cost=str(subtotal), price_status="estimate")
    return fields, subtotal


def recommend(db, user_id, body):
    body = freeze_quotes(db, user_id, body)
    today = date.today()
    preferences = db.get(UserPreference, user_id)
    servings = body.servings or preferences.default_servings
    minutes = body.max_minutes or preferences.max_minutes
    if body.scenario != "custom":
        presets = {
            "default": (60, 40, 10), "clear_fridge": (40, 80, 10),
            "quick": (60, 40, 10), "less_shopping": (100, 20, 10),
            "variety": (60, 40, 30),
        }
        inventory, expiry, repetition = presets[body.scenario]
        body = body.model_copy(update={"score_weights": ScoreWeights(
            inventory=inventory, expiry=expiry, repetition=repetition)})
        if body.scenario == "quick":
            minutes = min(minutes, 20)
    # One read for every candidate's history; the estimate never costs a query per recipe.
    samples = duration_samples(db, user_id, servings)
    personal_time_enabled = bool(preferences.personal_time_enabled)
    personalization_enabled = bool(preferences.personalization_enabled)
    preference_rows, preference_staples, preference_now = preference_history(db, user_id)
    equipment = {
        normalize(x)
        for x in (body.equipment if body.equipment is not None else preferences.equipment)
    }
    excluded = {normalize(x) for x in preferences.excluded_ingredients + body.excluded_ingredients}
    # Stored exclusions cannot be silently relaxed by a request. Resolve aliases within this user.
    forbidden = set(
        db.scalars(
            select(Ingredient.id).where(
                Ingredient.user_id == user_id, Ingredient.name.in_(excluded)
            )
        )
    )
    forbidden.update(
        db.scalars(
            select(IngredientAlias.ingredient_id).where(
                IngredientAlias.user_id == user_id, IngredientAlias.alias.in_(excluded)
            )
        )
    )
    quotes = {}
    for quote in body.quotes:
        ingredient = owned(db, Ingredient, quote.ingredient_id, user_id)
        convert(quote.package_quantity, ingredient.unit, ingredient.unit)
        quotes[ingredient.id] = quote
    batches = db.scalars(
        select(InventoryBatch).where(InventoryBatch.user_id == user_id).order_by(InventoryBatch.id)
    ).all()
    available, expiring = {}, {}
    for batch in batches:
        if batch.archived or (batch.expires_on is not None and batch.expires_on < today):
            continue
        available[batch.ingredient_id] = (
            available.get(batch.ingredient_id, Decimal(0)) + batch.quantity
        )
        if batch.expires_on is not None and batch.expires_on <= today + timedelta(days=3):
            expiring[batch.ingredient_id] = (
                expiring.get(batch.ingredient_id, Decimal(0)) + batch.quantity
            )
    recent = db.scalars(
        select(CookingRecord).where(
            CookingRecord.user_id == user_id,
            CookingRecord.status == "completed",
            CookingRecord.created_at >= today - timedelta(days=7),
        )
    ).all()
    repeats = {}
    for record in recent:
        rid = record.recipe_snapshot["id"]
        repeats[rid] = repeats.get(rid, 0) + 1
    candidates, rejected = [], []
    ids = db.scalars(select(Recipe.id).where(Recipe.user_id == user_id).order_by(Recipe.id)).all()
    feedbacks = feedback_map(db, user_id, [str(recipe_id) for recipe_id in ids])
    for recipe_id in ids:
        recipe = recipe_view(db, user_id, recipe_id)
        time_estimate = estimate(recipe, servings,
                                 samples.get((str(recipe_id), recipe["version"]), []),
                                 personal_time_enabled=personal_time_enabled)
        lines = selected_lines(recipe, body.include_optional)
        quantities = required_quantities(recipe, servings, body.include_optional)
        reasons = []
        if time_estimate["estimated_minutes"] > minutes:
            reasons.append("TIME_LIMIT")
        if not {normalize(x) for x in recipe["equipment"]} <= equipment:
            reasons.append("MISSING_EQUIPMENT")
        if any(x["ingredient_id"] in forbidden or normalize(x["name"]) in excluded for x in lines):
            reasons.append("EXCLUDED_INGREDIENT")
        if reasons:
            rejected.append({"recipe_id": recipe_id, "reasons": reasons})
            continue
        shopping, cost = [], Decimal(0)
        unknown = False
        coverage = Decimal(0)
        expiry_coverage = Decimal(0)
        for line in sorted(lines, key=lambda x: x["ingredient_id"]):
            iid = line["ingredient_id"]
            needed = quantities[iid]
            have = min(available.get(iid, Decimal(0)), needed)
            coverage += have / needed
            expiry_coverage += min(expiring.get(iid, Decimal(0)), needed) / needed
            missing = needed - have
            if missing <= 0:
                continue
            fields, subtotal = purchase_fields(missing, quotes.get(iid), today)
            cost += subtotal
            unknown = unknown or fields["price_status"] != "estimate"
            shopping.append({"ingredient_id": iid, "name": line["name"], "unit": line["unit"],
                             "missing_quantity": str(missing), **fields})
        budget_status = (
            "not_requested"
            if body.budget is None
            else ("exceeded" if cost > body.budget else "unknown" if unknown else "within_estimate")
        )
        if budget_status == "exceeded":
            rejected.append(
                {
                    "recipe_id": recipe_id,
                    "reasons": ["BUDGET_EXCEEDED"],
                    "known_purchase_cost": str(cost),
                }
            )
            continue
        # Normalize per ingredient, never add incompatible grams/ml/pieces.
        count = len(lines)
        components = {
            "inventory_coverage": float(coverage / count),
            "expiry_coverage": float(expiry_coverage / count),
            "recent_repetitions": repeats.get(recipe_id, 0),
            "purchase_cost": float(cost) if not unknown else None,
        }
        personalization = score_candidate(
            recipe, feedbacks.get(str(recipe_id)), preference_rows, preference_staples,
            candidate_ingredients={str(x["ingredient_id"]) for x in lines
                                   if not x.get("is_staple", False)},
            candidate_methods=recipe.get("cooking_methods", []),
            enabled=personalization_enabled, now=preference_now,
        )
        weights = body.score_weights
        base_score = (
            weights.inventory * components["inventory_coverage"]
            + weights.expiry * components["expiry_coverage"]
            - weights.repetition * components["recent_repetitions"]
            - weights.purchase_cost * (components["purchase_cost"] or 0)
        )
        score = base_score + personalization["preference_points"]
        candidates.append(
            {
                "recipe": recipe,
                "include_optional": body.include_optional,
                "omitted_optional": [
                    x["ingredient_id"]
                    for x in recipe["ingredients"]
                    if x.get("optional") and not body.include_optional
                ],
                "servings": servings,
                "time_estimate": time_estimate,
                "required_ingredients": [
                    {"ingredient_id": line["ingredient_id"], "name": line["name"],
                     "unit": line["unit"], "quantity": str(quantities[line["ingredient_id"]])}
                    for line in sorted(lines, key=lambda x: x["ingredient_id"])
                ],
                "shopping": shopping,
                "missing_ingredient_count": len(shopping),
                "known_purchase_cost": str(cost),
                "price_complete": not unknown,
                "budget_status": budget_status,
                "can_cook_now": not shopping,
                "score": round(score, 6),
                "score_components": components,
                "personalization": personalization,
                "base_score": round(base_score, 6),
                "score_weights": weights.model_dump(),
            }
        )
    candidates.sort(
        key=lambda c: (
            c["budget_status"] == "unknown",
            body.score_weights.purchase_cost > 0 and not c["price_complete"],
            c["missing_ingredient_count"] if body.scenario == "less_shopping" else 0,
            -c["score"],
            not c["price_complete"],
            Decimal(c["known_purchase_cost"]) if c["price_complete"] else Decimal(0),
            c["recipe"]["id"],
        )
    )
    return {
        "as_of": today.isoformat(),
        "constraints": {
            "scenario": body.scenario,
            "include_optional": body.include_optional,
            "servings": servings,
            "max_minutes": minutes,
            "equipment": sorted(equipment),
            "excluded_ingredients": sorted(excluded),
            "budget": str(body.budget) if body.budget is not None else None,
        },
        "candidates": candidates,
        "rejected": rejected,
        "rejection_counts": {
            reason: sum(reason in row["reasons"] for row in rejected)
            for reason in ("TIME_LIMIT", "MISSING_EQUIPMENT", "EXCLUDED_INGREDIENT", "BUDGET_EXCEEDED")
        },
        "budget_feasible": any(
            c["budget_status"] in ("within_estimate", "not_requested") for c in candidates
        ),
        "advisory_only": True,
        "personalization": {
            "enabled": personalization_enabled,
            "history_count": len(preference_rows),
            "window_days": 90,
        },
    }


def estimate_purchase(db, user_id, body):
    """Price a shortage the user stated, without inferring a recipe or servings."""
    ingredient = owned(db, Ingredient, body.ingredient_id, user_id)
    needed = convert(body.quantity, body.unit, ingredient.unit)
    quote = db.scalar(
        select(SavedQuote).where(SavedQuote.user_id == user_id,
                                 SavedQuote.ingredient_id == ingredient.id)
    )
    fields, subtotal = purchase_fields(needed, quote, date.today())
    return {
        "as_of": date.today().isoformat(),
        "ingredient": {"id": ingredient.id, "name": ingredient.name, "unit": ingredient.unit},
        "requested_quantity": str(body.quantity),
        "requested_unit": body.unit,
        "shortage_quantity": str(needed),
        "shortage_unit": ingredient.unit,
        **fields,
        "budget": str(body.budget) if body.budget is not None else None,
        "budget_status": (
            "not_requested" if body.budget is None
            else "exceeded" if fields["price_status"] == "estimate" and subtotal > body.budget
            else "unknown" if fields["price_status"] != "estimate"
            else "within_estimate"
        ),
        "advisory_only": True,
        "scope": "user_stated_shortage; no recipe, servings or inventory reservation",
    }
