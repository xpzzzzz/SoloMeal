"""Read-only previews for explicitly approved inventory mutations."""

import time
from decimal import Decimal

from sqlalchemy import select

from ..core.errors import AppError
from ..models.food import CookingConsumption, CookingRecord, Ingredient, InventoryBatch
from ..schemas.agent import UndoInput
from ..schemas.food import BatchInput, CookingInput
from ..schemas.planning import PlanningInput
from . import food, plans
from .planning import recommend
from .quantities import required_quantities

SCHEMAS = {"prepare_inventory": BatchInput, "prepare_cooking": CookingInput, "prepare_undo": UndoInput}


def preview(db, user_id, name, body, constraints=None):
    if name == "prepare_inventory":
        item = food.owned(db, Ingredient, body.ingredient_id, user_id)
        quantity = food.convert(body.quantity, body.unit, item.unit)
        state = {"ingredient_id": item.id, "name": item.name, "unit": item.unit}
        display = {"action": "入库", "name": item.name, "quantity": str(quantity), "unit": item.unit,
                   "location": body.location, "expires_on": body.expires_on.isoformat() if body.expires_on else None}
    elif name == "prepare_cooking":
        recipe = food.recipe_view(db, user_id, body.recipe_id)
        request = PlanningInput.model_validate({**(constraints or {}), "servings": body.servings,
                                                "include_optional": body.include_optional})
        options = recommend(db, user_id, request)
        candidate = next((c for c in options["candidates"] if c["recipe"]["id"] == str(body.recipe_id)), None)
        if candidate is None:
            raise AppError(409, "PLAN_INFEASIBLE", "Recipe does not satisfy current constraints")
        if candidate["budget_status"] == "unknown":
            raise AppError(409, "BUDGET_UNKNOWN", "Budget cannot be verified")
        if body.plan_id:
            plans.validate_confirmation(db, user_id, body)
        state = plans.state(db, user_id, recipe)
        needed = required_quantities(recipe, body.servings, body.include_optional)
        available = {}
        for batch in food.list_batches(db, user_id):
            if batch["expiry_status"] != "expired":
                iid = batch["ingredient_id"]
                available[iid] = available.get(iid, Decimal(0)) + Decimal(batch["quantity"])
        if any(available.get(iid, Decimal(0)) < qty for iid, qty in needed.items()):
            raise AppError(409, "INSUFFICIENT_STOCK", "Not enough usable inventory")
        display = {"action": "记录做饭", "name": recipe["name"], "servings": body.servings,
                   "ingredients": [{"name": line["name"], "quantity": str(needed[line["ingredient_id"]]),
                                    "unit": line["unit"]} for line in recipe["ingredients"]
                                   if line["ingredient_id"] in needed]}
    else:
        record = food.owned(db, CookingRecord, body.cooking_id, user_id)
        if record.status != "completed":
            raise AppError(409, "COOKING_RETRACTED", "Cooking record was already retracted")
        lines = db.scalars(select(CookingConsumption).where(
            CookingConsumption.cooking_id == record.id, CookingConsumption.user_id == user_id,
        ).order_by(CookingConsumption.batch_id)).all()
        batches = [food.owned(db, InventoryBatch, line.batch_id, user_id) for line in lines]
        state = {"cooking_id": record.id, "status": record.status,
                 "batches": [{"id": b.id, "version": b.version, "archived": b.archived,
                              "quantity": str(b.quantity)} for b in batches]}
        display = {"action": "撤销做饭并恢复食材", "name": record.recipe_snapshot["name"],
                   "ingredients": [{"name": food.owned(db, Ingredient, b.ingredient_id, user_id).name,
                                    "quantity": str(line.quantity),
                                    "unit": food.owned(db, Ingredient, b.ingredient_id, user_id).unit,
                                    "archived": b.archived} for line, b in zip(lines, batches)]}
    return {"kind": name, "request": body.model_dump(mode="json"), "state": state,
            "constraints": constraints or {}, "preview": display, "expires_at": int(time.time()) + 900}


def approve(db, user_id, key, pending, operation):
    name = pending["kind"]
    if int(time.time()) > pending["expires_at"]:
        raise AppError(409, "CONFIRMATION_EXPIRED", "Confirmation expired; prepare the action again")
    body = SCHEMAS[name].model_validate(pending["request"])
    current = preview(db, user_id, name, body, pending.get("constraints"))
    if current["state"] != pending["state"]:
        raise AppError(409, "PLAN_STALE", "Action targets changed; prepare the action again")
    if name == "prepare_inventory":
        return food.add_batch(db, user_id, key, body, operation=operation)
    if name == "prepare_cooking":
        return food.cook(db, user_id, key, body, operation=operation)
    return food.undo(db, user_id, key, body.cooking_id, operation=operation)
