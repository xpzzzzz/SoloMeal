from datetime import date
from decimal import Decimal

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import select

from ..core.errors import AppError
from ..models.food import Ingredient
from ..models.plans import MealPlan
from ..models.shopping import SavedQuote, ShoppingList
from ..schemas.food import BatchInput
from ..schemas.shopping import PurchaseItem
from . import food, personal_time, plans


def quote_view(db, row):
    item = food.owned(db, Ingredient, row.ingredient_id, row.user_id)
    return {"id": row.id, "ingredient_id": item.id, "name": item.name, "unit": item.unit,
            "package_quantity": str(row.package_quantity), "package_price": str(row.package_price),
            "currency": row.currency, "source": row.source, "observed_on": row.observed_on.isoformat(),
            "version": row.version, "price_status": "stale" if (date.today() - row.observed_on).days > 30 else "estimate"}


def save_quote(db, user_id, key, body):
    def action(op):
        item = food.owned(db, Ingredient, body.ingredient_id, user_id)
        food.convert(body.package_quantity, item.unit, item.unit)
        row = db.scalar(select(SavedQuote).where(SavedQuote.user_id == user_id,
                                               SavedQuote.ingredient_id == item.id))
        if (row.version if row else 0) != body.expected_version:
            raise AppError(409, "VERSION_CONFLICT", "Quote changed; refresh before saving")
        if row is None:
            row = SavedQuote(user_id=user_id, ingredient_id=item.id, version=1)
            db.add(row)
        else:
            row.version += 1
        for field in ("package_quantity", "package_price", "currency", "source", "observed_on"):
            setattr(row, field, getattr(body, field))
        db.flush()
        return quote_view(db, row)
    return food.run_operation(db, user_id, key, "save_quote", body.model_dump(mode="json"), action)


def view(row):
    return {"id": row.id, "version": row.version, "status": row.status, "origin": row.origin,
            "items": row.items, "checked_ingredient_ids": row.checked_ingredient_ids,
            "result": row.result, "created_at": row.created_at}


def create(db, user_id, key, body):
    def action(op):
        plan = food.owned(db, MealPlan, body.plan_id, user_id)
        if plan.status != "pending" or plan.version != body.expected_version:
            raise AppError(409, "PLAN_CONFLICT", "Plan changed; refresh before preparing shopping")
        for existing in db.scalars(select(ShoppingList).where(ShoppingList.user_id == user_id)):
            if (existing.origin.get("kind", "single_plan") == "single_plan"
                    and existing.origin.get("plan_id") == plan.id
                    and existing.origin.get("plan_version") == plan.version):
                return view(existing)
        snapshot = plans.revision(db, plan).snapshot
        candidate = snapshot["candidate"]
        current_recipe = food.recipe_view(db, user_id, candidate["recipe"]["id"])
        if snapshot["state"] != plans.state(db, user_id, current_recipe, personal_time.effective(
                db, user_id, current_recipe, candidate["servings"])):
            raise AppError(409, "PLAN_STALE", "Revise the plan before preparing shopping")
        if not candidate["shopping"]:
            raise AppError(409, "NO_SHOPPING_NEEDED", "This plan has no missing ingredients")
        items = [{"ingredient_id": line["ingredient_id"], "name": line["name"],
                  "quantity": line["purchase_quantity"] or line["missing_quantity"],
                  "unit": line["unit"], "actual_cost": None, "currency": "CNY",
                  "expires_on": None, "expiry_source": "unknown", "location": "fridge"}
                 for line in candidate["shopping"]]
        try:
            for item in items:
                PurchaseItem.model_validate({k: v for k, v in item.items() if k != "name"})
        except ValidationError as exc:
            raise AppError(422, "QUANTITY_TOO_LARGE", "Suggested purchase exceeds input capacity; reduce servings") from exc
        row = ShoppingList(user_id=user_id, items=items, origin={
            "kind": "single_plan", "plan_id": plan.id, "plan_version": plan.version, "recipe_name": candidate["recipe"]["name"],
            "budget": snapshot["constraints"]["budget"], "shopping": candidate["shopping"]})
        db.add(row)
        db.flush()
        return view(row)
    return food.run_operation(db, user_id, key, "create_shopping", body.model_dump(mode="json"), action)


def change(db, user_id, key, list_id, body, kind):
    def action(op):
        row = food.owned(db, ShoppingList, list_id, user_id, lock=True)
        if row.status != "draft" or row.version != body.expected_version:
            raise AppError(409, "SHOPPING_CONFLICT", "Shopping list changed; reload before continuing")
        if kind == "edit":
            result = []
            for line in body.items:
                item = food.owned(db, Ingredient, line.ingredient_id, user_id)
                food.convert(line.quantity, line.unit, item.unit)
                result.append({**line.model_dump(mode="json"), "name": item.name})
            row.items = result
            row.checked_ingredient_ids = [iid for iid in row.checked_ingredient_ids
                                          if iid in {x["ingredient_id"] for x in result}]
        elif kind == "check":
            ids = {str(iid) for iid in body.checked_ingredient_ids}
            if not ids <= {x["ingredient_id"] for x in row.items}:
                raise AppError(422, "INVALID_SHOPPING_CHECK", "Only current shopping items can be checked")
            row.checked_ingredient_ids = sorted(ids)
        elif kind == "close":
            row.status = "closed"
        elif kind == "cancel":
            row.status = "cancelled"
        else:
            if (row.origin.get("kind") == "recipe_combination"
                    and set(row.checked_ingredient_ids) != {x["ingredient_id"] for x in row.items}):
                raise AppError(409, "SHOPPING_UNCHECKED", "Check all purchased items before confirming")
            lines = [PurchaseItem.model_validate({k: v for k, v in line.items() if k != "name"})
                     for line in row.items]
            budget = row.origin.get("budget")
            if budget is not None:
                if any(line.actual_cost is None for line in lines):
                    raise AppError(409, "BUDGET_UNKNOWN", "Enter actual costs before confirming this budgeted purchase")
                if sum(line.actual_cost for line in lines) > Decimal(budget):
                    raise AppError(409, "BUDGET_EXCEEDED", "Actual purchase cost exceeds the plan budget")
            batches = []
            for line in lines:
                batch = BatchInput.model_validate(line.model_dump(exclude={"actual_cost", "currency"}))
                batches.append(food.add_batch(db, user_id, key, batch, operation=op))
            row.result = jsonable_encoder({"batches": batches})
            row.status = "completed"
        row.version += 1
        db.flush()
        return view(row)
    return food.run_operation(db, user_id, key, "shopping_" + kind,
                              {"list_id": str(list_id), **body.model_dump(mode="json")}, action)
