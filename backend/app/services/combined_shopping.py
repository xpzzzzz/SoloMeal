"""Read-only combined demand; creation rechecks it under the owner mutation lock."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import select

from ..core.errors import AppError
from ..models.food import InventoryBatch
from ..models.shopping import SavedQuote, ShoppingList
from ..schemas.shopping import PurchaseItem
from . import food, shopping
from .planning import purchase_fields
from .quantities import required_quantities, selected_lines


def preview(db, user_id, body):
    today = datetime.now(timezone.utc).date()
    demand, contributions, ingredients, recipes = {}, {}, {}, []
    for choice in sorted(body.recipes, key=lambda r: str(r.recipe_id)):
        recipe = food.recipe_view(db, user_id, choice.recipe_id)
        if recipe["version"] != choice.version:
            raise AppError(409, "COMBINATION_STALE", "Recipe changed; refresh the combination")
        recipes.append({**choice.model_dump(mode="json"), "name": recipe["name"]})
        quantities = required_quantities(recipe, choice.servings, choice.include_optional)
        for line in selected_lines(recipe, choice.include_optional):
            iid = line["ingredient_id"]
            ingredients[iid] = line
            demand[iid] = demand.get(iid, Decimal(0)) + quantities[iid]
            contributions.setdefault(iid, []).append({"recipe_id": recipe["id"],
                "name": recipe["name"], "quantity": str(quantities[iid])})
    available, batch_state = {}, []
    for batch in db.scalars(select(InventoryBatch).where(
            InventoryBatch.user_id == user_id, InventoryBatch.ingredient_id.in_(demand)
    ).order_by(InventoryBatch.id)):
        if batch.archived or (batch.expires_on is not None and batch.expires_on < today):
            continue
        available[batch.ingredient_id] = available.get(batch.ingredient_id, Decimal(0)) + batch.quantity
        batch_state.append([batch.id, batch.version, str(batch.quantity),
                            batch.expires_on.isoformat() if batch.expires_on else None])
    quotes = {q.ingredient_id: q for q in db.scalars(select(SavedQuote).where(
        SavedQuote.user_id == user_id, SavedQuote.ingredient_id.in_(demand)))}
    lines, cost, unknown = [], Decimal(0), False
    for iid in sorted(demand):
        have = available.get(iid, Decimal(0))
        missing = max(Decimal(0), demand[iid] - have)
        fields, subtotal = purchase_fields(missing, quotes.get(iid), today)
        cost += subtotal
        unknown = unknown or (missing > 0 and fields["price_status"] != "estimate")
        lines.append({"ingredient_id": iid, "name": ingredients[iid]["name"],
            "unit": ingredients[iid]["unit"], "required_quantity": str(demand[iid]),
            "available_quantity": str(have), "missing_quantity": str(missing),
            "contributions": contributions[iid], **fields})
    state = {"user_id": str(user_id), "as_of": today.isoformat(), "recipes": recipes,
        "budget": str(body.budget) if body.budget is not None else None,
        "lines": lines, "batches": batch_state,
        "quotes": [[iid, q.version, str(q.package_quantity), str(q.package_price),
                    q.source, q.observed_on.isoformat()] for iid, q in sorted(quotes.items())]}
    signature = hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"signature": signature, "as_of": today.isoformat(), "recipes": recipes,
        "budget": state["budget"], "lines": lines, "known_purchase_cost": str(cost),
        "price_complete": not unknown, "budget_status": "not_requested" if body.budget is None
        else "exceeded" if cost > body.budget else "unknown" if unknown else "within_estimate"}


def create(db, user_id, key, body):
    def action(op):
        current = preview(db, user_id, body)
        if current["signature"] != body.signature:
            raise AppError(409, "COMBINATION_STALE", "Inventory or quotes changed; calculate again")
        needed = [line for line in current["lines"] if Decimal(line["missing_quantity"]) > 0]
        if not needed:
            raise AppError(409, "NO_SHOPPING_NEEDED", "No missing ingredients")
        items = []
        try:
            for line in needed:
                item = PurchaseItem(ingredient_id=line["ingredient_id"],
                    quantity=line["purchase_quantity"] or line["missing_quantity"],
                    unit=line["unit"], location="fridge", expiry_source="unknown")
                items.append({**item.model_dump(mode="json"), "name": line["name"]})
        except ValidationError as exc:
            raise AppError(422, "QUANTITY_TOO_LARGE", "Suggested purchase exceeds input capacity") from exc
        if len(items) > 100:
            raise AppError(422, "COMBINATION_TOO_LARGE", "At most 100 shopping ingredients")
        row = ShoppingList(user_id=user_id, items=items, origin={
            "kind": "recipe_combination", "recipe_name": "多菜采购组合",
            **current, "shopping": needed})
        db.add(row)
        db.flush()
        return shopping.view(row)
    return food.run_operation(db, user_id, key, "create_combined_shopping", body.model_dump(mode="json"), action)
