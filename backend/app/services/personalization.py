"""Deterministic, explainable preference scoring from a user's cooking history."""

from datetime import timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from ..models.food import CookingRecord, Ingredient, utcnow

WINDOW_DAYS = 90
MAX_RECORDS = 200
# Asia/Shanghai has no DST; a fixed offset keeps the rule portable on Windows
# where the optional IANA tzdata package is not necessarily installed.
SHANGHAI = timezone(timedelta(hours=8))


def _local_day(value):
    return value.replace(tzinfo=timezone.utc).astimezone(SHANGHAI).date()


def history(db, user_id, *, now=None):
    """Return the de-duplicated records and their owned staple lookup in one batch."""
    now = now or utcnow()
    rows = db.scalars(
        select(CookingRecord)
        .where(
            CookingRecord.user_id == user_id,
            CookingRecord.status == "completed",
            CookingRecord.created_at >= now - timedelta(days=WINDOW_DAYS),
        )
        .order_by(CookingRecord.created_at.desc(), CookingRecord.id.desc())
        .limit(MAX_RECORDS)
    ).all()
    seen = set()
    selected = []
    for row in rows:
        snapshot = row.recipe_snapshot or {}
        key = (str(snapshot.get("id", "")), _local_day(row.created_at))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) >= MAX_RECORDS:
            break
    ingredient_ids = {
        str(line.get("ingredient_id"))
        for row in selected
        for line in (row.recipe_snapshot or {}).get("ingredients", [])
        if line.get("ingredient_id")
    }
    staples = {
        str(i.id): bool(i.is_staple)
        for i in db.scalars(
            select(Ingredient).where(Ingredient.user_id == user_id, Ingredient.id.in_(ingredient_ids))
        )
    } if ingredient_ids else {}
    return selected, staples, now


def _features(row, staples):
    snapshot = row.recipe_snapshot or {}
    include_optional = bool(snapshot.get("include_optional", False))
    ingredients = {
        str(line.get("ingredient_id"))
        for line in snapshot.get("ingredients", [])
        if line.get("ingredient_id")
        and (include_optional or not line.get("optional", False))
        and not staples.get(str(line.get("ingredient_id")), False)
    }
    methods = set(snapshot.get("cooking_methods") or [])
    return ingredients, methods


def _weights(rows, staples, *, now):
    total = Decimal(0)
    ingredients = {}
    methods = {}
    ingredient_counts = {}
    method_counts = {}
    for row in rows:
        age_days = max(Decimal(0), Decimal((now - row.created_at).total_seconds()) / Decimal(86400))
        weight = Decimal(2) ** (-age_days / Decimal(30))
        total += weight
        row_ingredients, row_methods = _features(row, staples)
        for ingredient_id in row_ingredients:
            ingredients[ingredient_id] = ingredients.get(ingredient_id, Decimal(0)) + weight
            ingredient_counts[ingredient_id] = ingredient_counts.get(ingredient_id, 0) + 1
        for method in row_methods:
            methods[method] = methods.get(method, Decimal(0)) + weight
            method_counts[method] = method_counts.get(method, 0) + 1
    if not total:
        return {}, {}, {}, {}, Decimal(0)
    return (
        {key: value / total for key, value in ingredients.items()},
        {key: value / total for key, value in methods.items()},
        ingredient_counts,
        method_counts,
        total,
    )


def _points(value):
    return round(float(value), 6)


def score_candidate(recipe, feedback, rows, staples, *, candidate_ingredients=None,
                    candidate_methods=None, enabled=True, now=None):
    now = now or utcnow()
    ingredient_affinity, method_affinity, ingredient_counts, method_counts, _ = _weights(
        rows, staples, now=now
    )
    candidate_ingredients = candidate_ingredients if candidate_ingredients is not None else {
        str(line["ingredient_id"])
        for line in recipe.get("ingredients", [])
        if not line.get("optional", False) and not staples.get(str(line["ingredient_id"]), False)
    }
    candidate_methods = set(candidate_methods if candidate_methods is not None else recipe.get("cooking_methods") or [])
    ingredient_value = (
        sum(ingredient_affinity.get(key, Decimal(0)) for key in candidate_ingredients)
        / len(candidate_ingredients)
        if candidate_ingredients else None
    )
    method_value = (
        sum(method_affinity.get(key, Decimal(0)) for key in candidate_methods) / len(candidate_methods)
        if candidate_methods else None
    )
    if ingredient_value is not None and method_value is not None:
        affinity = Decimal("0.7") * ingredient_value + Decimal("0.3") * method_value
    else:
        affinity = ingredient_value if ingredient_value is not None else method_value or Decimal(0)
    confidence = min(Decimal(1), Decimal(len(rows)) / Decimal(5))
    implicit = Decimal(10) * confidence * affinity if enabled else Decimal(0)
    explicit = Decimal(0)
    if feedback:
        if feedback.get("rating") == "dislike":
            explicit = Decimal(-15)
        else:
            explicit = (Decimal(3) if feedback.get("favorite") else Decimal(0))
            explicit += Decimal(5) if feedback.get("rating") == "like" else Decimal(0)
    preference = max(Decimal(-15), min(Decimal(15), implicit + explicit)) if enabled else Decimal(0)
    reasons = []
    if enabled and rows:
        if ingredient_value and ingredient_value > 0:
            used = sorted(
                ((ingredient_affinity.get(key, Decimal(0)), key) for key in candidate_ingredients), reverse=True
            )
            if used:
                reasons.append({
                    "type": "ingredient", "value": _points(used[0][0]),
                    "ingredient_id": used[0][1],
                    "occurrence_count": ingredient_counts.get(used[0][1], 0),
                    "window_count": len(rows),
                })
        if method_value and method_value > 0:
            used = sorted(
                ((method_affinity.get(key, Decimal(0)), key) for key in candidate_methods), reverse=True
            )
            if used:
                reasons.append({
                    "type": "method", "value": _points(used[0][0]),
                    "method": used[0][1],
                    "occurrence_count": method_counts.get(used[0][1], 0),
                    "window_count": len(rows),
                })
    if feedback and feedback.get("rating") == "dislike":
        reasons.insert(0, {"type": "feedback", "value": -15, "rating": "dislike"})
    elif feedback and (feedback.get("favorite") or feedback.get("rating") == "like"):
        reasons.insert(0, {"type": "feedback", "value": _points(explicit), "rating": feedback.get("rating")})
    return {
        "enabled": enabled,
        "history_count": len(rows),
        "ingredient_affinity": _points(ingredient_value or Decimal(0)),
        "method_affinity": _points(method_value or Decimal(0)),
        "confidence": _points(confidence),
        "implicit_points": _points(implicit),
        "explicit_points": _points(explicit),
        "preference_points": _points(preference),
        "reasons": reasons[:2],
    }


def summary(db, user_id, *, enabled=True):
    rows, staples, now = history(db, user_id)
    ingredients, methods, ingredient_counts, method_counts, _ = _weights(rows, staples, now=now)
    return {
        "enabled": enabled,
        "history_count": len(rows),
        "window_days": WINDOW_DAYS,
        "top_ingredients": [{"ingredient_id": key, "affinity": _points(value),
                             "occurrence_count": ingredient_counts.get(key, 0),
                             "window_count": len(rows)}
                            for key, value in sorted(ingredients.items(), key=lambda x: (-x[1], x[0]))[:5]],
        "top_methods": [{"method": key, "affinity": _points(value),
                         "occurrence_count": method_counts.get(key, 0),
                         "window_count": len(rows)}
                        for key, value in sorted(methods.items(), key=lambda x: (-x[1], x[0]))[:5]],
        "message": "偏好仍在积累" if len(rows) < 5 else "基于最近完成记录",
    }
