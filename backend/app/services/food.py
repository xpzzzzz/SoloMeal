import hashlib
import json
from datetime import date
from decimal import Decimal

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from ..core.errors import AppError
from ..models.food import (
    CookingConsumption,
    CookingRecord,
    Ingredient,
    IngredientAlias,
    InventoryBatch,
    InventoryEvent,
    Operation,
    Recipe,
    RecipeFeedback,
    RecipeIngredient,
    utcnow,
)
from ..models.identity import User
from .quantities import required_quantities


def owned(db, model, object_id, user_id, lock=False):
    query = select(model).where(model.id == str(object_id), model.user_id == user_id)
    if lock:
        query = query.with_for_update()
    obj = db.scalar(query)
    if obj is None:
        raise AppError(404, "NOT_FOUND", "Object not found")
    return obj


def normalize(value):
    return value.strip().lower()


def convert(quantity, unit, target):
    units = {
        "g": ("g", Decimal(1)),
        "kg": ("g", Decimal(1000)),
        "ml": ("ml", Decimal(1)),
        "l": ("ml", Decimal(1000)),
        "piece": ("piece", Decimal(1)),
    }
    base, factor = units[unit]
    if base != target:
        raise AppError(422, "UNIT_AMBIGUOUS", "Cannot convert between count, mass and volume")
    result = quantity * factor
    if result > Decimal("99999999999.999"):
        raise AppError(422, "QUANTITY_TOO_LARGE", "Quantity exceeds storage capacity")
    if target == "piece" and result != result.to_integral_value():
        raise AppError(422, "UNIT_AMBIGUOUS", "Piece counts must be whole numbers")
    return result


def run_operation(db, user_id, key, kind, payload, action):
    digest = hashlib.sha256(
        json.dumps({"kind": kind, "payload": payload}, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()

    def existing():
        return db.scalar(
            select(Operation).where(Operation.user_id == user_id, Operation.key == key)
        )

    def replay(op):
        if op.request_hash != digest:
            raise AppError(
                409, "IDEMPOTENCY_CONFLICT", "Key was already used with different parameters"
            )
        return op.result

    try:
        # Serialize owner mutations; different users remain independent.
        db.scalar(select(User).where(User.id == user_id).with_for_update())
        db.expire_all()
        prior = existing()
        if prior:
            return replay(prior)
        op = Operation(user_id=user_id, key=key, kind=kind, request_hash=digest)
        db.add(op)
        db.flush()
        op.result = jsonable_encoder(action(op))
        db.commit()
        return op.result
    except IntegrityError as exc:
        db.rollback()
        prior = existing()
        if prior:
            return replay(prior)
        raise AppError(409, "CONFLICT", "Conflicting operation") from exc
    except Exception:
        db.rollback()
        raise


def add_ingredient(db, user_id, body):
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    name = normalize(body.name)
    if db.scalar(
        select(IngredientAlias).where(
            IngredientAlias.user_id == user_id, IngredientAlias.alias == name
        )
    ):
        raise AppError(409, "NAME_CONFLICT", "Name already belongs to an alias")
    obj = Ingredient(user_id=user_id, name=name, unit=body.unit, is_staple=body.is_staple)
    db.add(obj)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "NAME_CONFLICT", "Ingredient name already exists") from exc
    return {"id": obj.id, "name": obj.name, "unit": obj.unit, "is_staple": obj.is_staple}


def add_alias(db, user_id, ingredient_id, body):
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    item = owned(db, Ingredient, ingredient_id, user_id)
    label = normalize(body.alias)
    if db.scalar(select(Ingredient).where(Ingredient.user_id == user_id, Ingredient.name == label)):
        raise AppError(409, "NAME_CONFLICT", "Alias conflicts with an ingredient name")
    obj = IngredientAlias(user_id=user_id, ingredient_id=item.id, alias=label)
    db.add(obj)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "NAME_CONFLICT", "Alias already exists") from exc
    return {"id": obj.id, "ingredient_id": item.id, "alias": label}


def resolve(db, user_id, name):
    label = normalize(name)
    item = db.scalar(
        select(Ingredient).where(Ingredient.user_id == user_id, Ingredient.name == label)
    )
    if not item:
        alias = db.scalar(
            select(IngredientAlias).where(
                IngredientAlias.user_id == user_id, IngredientAlias.alias == label
            )
        )
        if alias:
            item = owned(db, Ingredient, alias.ingredient_id, user_id)
    if not item:
        raise AppError(404, "NOT_FOUND", "Ingredient not found")
    return {"id": item.id, "name": item.name, "unit": item.unit}


def batch_view(batch, item):
    today = date.today()
    expiry = (
        "unknown"
        if batch.expires_on is None
        else "expired"
        if batch.expires_on < today
        else "expiring_soon"
        if (batch.expires_on - today).days <= 3
        else "fresh"
    )
    return {
        "id": batch.id,
        "ingredient_id": batch.ingredient_id,
        "name": item.name,
        "quantity": str(batch.quantity),
        "unit": item.unit,
        "expires_on": batch.expires_on.isoformat() if batch.expires_on else None,
        "expiry_source": batch.expiry_source,
        "expiry_status": expiry,
        "location": batch.location,
        "version": batch.version,
        "archived": batch.archived,
    }


def list_batches(db, user_id, include_archived=False, *, limit=None, offset=0):
    rows = db.execute(
        select(InventoryBatch, Ingredient)
        .join(Ingredient, InventoryBatch.ingredient_id == Ingredient.id)
        .where(InventoryBatch.user_id == user_id)
        .where(True if include_archived else InventoryBatch.archived.is_(False))
        .order_by(InventoryBatch.created_at, InventoryBatch.id).limit(limit).offset(offset)
    )
    return [batch_view(b, i) for b, i in rows]


def add_batch(db, user_id, key, body, *, operation=None):
    def action(op):
        ingredient = owned(db, Ingredient, body.ingredient_id, user_id)
        qty = convert(body.quantity, body.unit, ingredient.unit)
        batch = InventoryBatch(
            user_id=user_id,
            ingredient_id=ingredient.id,
            quantity=qty,
            expires_on=body.expires_on,
            expiry_source=body.expiry_source,
            location=body.location,
        )
        db.add(batch)
        db.flush()
        db.add(
            InventoryEvent(
                user_id=user_id, batch_id=batch.id, operation_id=op.id, delta=qty, reason="purchase",
                batch_version=batch.version,
            )
        )
        return batch_view(batch, ingredient)

    if operation is not None:
        return action(operation)
    return run_operation(db, user_id, key, "add_batch", body.model_dump(mode="json"), action)


def adjust_batch(db, user_id, key, batch_id, body):
    def action(op):
        batch = owned(db, InventoryBatch, batch_id, user_id, lock=True)
        if batch.version != body.expected_version:
            raise AppError(409, "VERSION_CONFLICT", "Inventory changed; refresh before adjusting")
        if batch.archived:
            raise AppError(409, "BATCH_ARCHIVED", "Restore the batch before adjusting")
        item = owned(db, Ingredient, batch.ingredient_id, user_id)
        qty = batch.quantity if body.quantity is None else convert(body.quantity, item.unit, item.unit)
        delta = qty - batch.quantity
        batch.quantity = qty
        for field in ("expires_on", "expiry_source", "location"):
            if field in body.model_fields_set:
                setattr(batch, field, getattr(body, field))
        batch.version += 1
        db.add(
            InventoryEvent(
                user_id=user_id,
                batch_id=batch.id,
                operation_id=op.id,
                delta=delta,
                reason="adjustment",
                batch_version=batch.version,
            )
        )
        return batch_view(batch, item)

    return run_operation(
        db,
        user_id,
        key,
        "adjust_batch",
        {"batch_id": str(batch_id), **body.model_dump(mode="json", exclude_unset=True)},
        action,
    )


def add_recipe(db, user_id, body, *, source_type="manual", source_ref=None):
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    try:
        recipe_id = insert_recipe(
            db, user_id, body, source_type=source_type, source_ref=source_ref
        )
        db.commit()
        return recipe_view(db, user_id, recipe_id)
    except Exception:
        db.rollback()
        raise


def insert_recipe(db, user_id, body, *, source_type="manual", source_ref=None):
    """Insert a recipe and its lines in the caller's transaction; commit stays outside."""
    ids = [str(i.ingredient_id) for i in body.ingredients]
    if len(ids) != len(set(ids)):
        raise AppError(422, "DUPLICATE_INGREDIENT", "Recipe ingredients must be unique")
    lines = []
    for line in body.ingredients:
        item = owned(db, Ingredient, line.ingredient_id, user_id)
        lines.append((item.id, convert(line.quantity, line.unit, item.unit), line.optional))
    recipe = Recipe(
        user_id=user_id,
        name=body.name,
        servings=body.servings,
        minutes=body.minutes,
        equipment=body.equipment,
        steps=body.steps,
        source=body.source,
        source_type=source_type,
        source_ref=source_ref,
        cooking_methods=list(body.cooking_methods),
    )
    db.add(recipe)
    db.flush()
    for item_id, qty, optional in lines:
        db.add(
            RecipeIngredient(
                user_id=user_id,
                recipe_id=recipe.id,
                ingredient_id=item_id,
                quantity=qty,
                optional=optional,
            )
        )
    db.flush()
    return recipe.id


def archive_batch(db, user_id, key, batch_id, body):
    def action(op):
        batch = owned(db, InventoryBatch, batch_id, user_id, lock=True)
        if batch.version != body.expected_version:
            raise AppError(409, "VERSION_CONFLICT", "Inventory changed; refresh before archiving")
        if batch.archived != body.archived:
            batch.archived = body.archived
            batch.version += 1
            db.add(InventoryEvent(
                user_id=user_id, batch_id=batch.id, operation_id=op.id,
                delta=Decimal(0), reason="archive" if body.archived else "restore",
                batch_version=batch.version,
            ))
        return batch_view(batch, owned(db, Ingredient, batch.ingredient_id, user_id))

    return run_operation(db, user_id, key, "archive_batch",
                         {"batch_id": str(batch_id), **body.model_dump()}, action)


def update_recipe(db, user_id, key, recipe_id, body):
    def action(op):
        recipe = owned(db, Recipe, recipe_id, user_id, lock=True)
        if recipe.version != body.expected_version:
            raise AppError(409, "VERSION_CONFLICT", "Recipe changed; refresh before editing")
        ids = [str(line.ingredient_id) for line in body.ingredients]
        if len(ids) != len(set(ids)):
            raise AppError(422, "DUPLICATE_INGREDIENT", "Recipe ingredients must be unique")
        lines = []
        for line in body.ingredients:
            item = owned(db, Ingredient, line.ingredient_id, user_id)
            lines.append((item.id, convert(line.quantity, line.unit, item.unit), line.optional))
        db.execute(delete(RecipeIngredient).where(
            RecipeIngredient.recipe_id == recipe.id, RecipeIngredient.user_id == user_id,
        ))
        for field in ("name", "servings", "minutes", "equipment", "steps", "source",
                      "cooking_methods"):
            setattr(recipe, field, getattr(body, field))
        recipe.version += 1
        for item_id, qty, optional in lines:
            db.add(RecipeIngredient(user_id=user_id, recipe_id=recipe.id,
                                   ingredient_id=item_id, quantity=qty, optional=optional))
        db.flush()
        return recipe_view(db, user_id, recipe.id)

    return run_operation(db, user_id, key, "update_recipe",
                         {"recipe_id": str(recipe_id), **body.model_dump(mode="json")}, action)


def delete_recipe(db, user_id, key, recipe_id, body):
    def action(op):
        recipe = owned(db, Recipe, recipe_id, user_id, lock=True)
        if recipe.version != body.expected_version:
            raise AppError(409, "VERSION_CONFLICT", "Recipe changed; refresh before deleting")
        # Plans and cooking records retain immutable JSON snapshots, not recipe foreign keys.
        db.execute(delete(RecipeIngredient).where(
            RecipeIngredient.recipe_id == recipe.id, RecipeIngredient.user_id == user_id,
        ))
        # Feedback is state about this row only, so it goes with it; snapshots above do not.
        db.execute(delete(RecipeFeedback).where(
            RecipeFeedback.recipe_id == recipe.id, RecipeFeedback.user_id == user_id,
        ))
        db.delete(recipe)
        return {"id": str(recipe_id), "status": "deleted"}

    return run_operation(db, user_id, key, "delete_recipe",
                         {"recipe_id": str(recipe_id), **body.model_dump()}, action)


def recipe_view(db, user_id, recipe_id):
    recipe = owned(db, Recipe, recipe_id, user_id)
    lines = db.execute(
        select(RecipeIngredient, Ingredient)
        .join(Ingredient, RecipeIngredient.ingredient_id == Ingredient.id)
        .where(RecipeIngredient.recipe_id == recipe.id, RecipeIngredient.user_id == user_id)
        .order_by(Ingredient.id)
    )
    return {
        "id": recipe.id,
        "name": recipe.name,
        "servings": recipe.servings,
        "minutes": recipe.minutes,
        "equipment": recipe.equipment,
        "steps": recipe.steps,
        "source": recipe.source,
        "source_type": recipe.source_type,
        "source_ref": recipe.source_ref,
        "cooking_methods": list(recipe.cooking_methods or []),
        "version": recipe.version,
        "ingredients": [
            {
                "ingredient_id": i.id,
                "name": i.name,
                "unit": i.unit,
                "quantity": str(line.quantity),
                "optional": line.optional,
                "is_staple": i.is_staple,
            }
            for line, i in lines
        ],
    }


def empty_feedback(recipe_id):
    """What a recipe with no row reads as: not favorite, no rating, ready for version 0."""
    return {
        "recipe_id": str(recipe_id),
        "favorite": False,
        "rating": "neutral",
        "version": 0,
        "updated_at": None,
    }


def feedback_view(row):
    return {
        "recipe_id": row.recipe_id,
        "favorite": row.favorite,
        "rating": row.rating,
        "version": row.version,
        "updated_at": row.updated_at,
    }


def get_feedback(db, user_id, recipe_id):
    owned(db, Recipe, recipe_id, user_id)
    row = db.scalar(
        select(RecipeFeedback).where(
            RecipeFeedback.user_id == user_id, RecipeFeedback.recipe_id == str(recipe_id)
        )
    )
    return feedback_view(row) if row else empty_feedback(recipe_id)


def feedback_map(db, user_id, recipe_ids):
    """One read for a whole list, so the page never asks per recipe."""
    if not recipe_ids:
        return {}
    rows = db.scalars(
        select(RecipeFeedback).where(
            RecipeFeedback.user_id == user_id, RecipeFeedback.recipe_id.in_(recipe_ids)
        )
    )
    return {row.recipe_id: feedback_view(row) for row in rows}


def set_feedback(db, user_id, key, recipe_id, body):
    def action(op):
        owned(db, Recipe, recipe_id, user_id)
        row = db.scalar(
            select(RecipeFeedback).where(
                RecipeFeedback.user_id == user_id, RecipeFeedback.recipe_id == str(recipe_id)
            )
        )
        if row is None:
            if body.expected_version != 0:
                raise AppError(409, "VERSION_CONFLICT", "Feedback changed; refresh before saving")
            row = RecipeFeedback(user_id=user_id, recipe_id=str(recipe_id), version=0)
            db.add(row)
        elif row.version != body.expected_version:
            raise AppError(409, "VERSION_CONFLICT", "Feedback changed; refresh before saving")
        # The whole state is written every time, so switching replaces instead of adding.
        row.favorite = body.favorite
        row.rating = body.rating
        row.version += 1
        # MySQL's default DATETIME precision is seconds. Match the immediate
        # response to what a later read (or an idempotent replay) will return.
        row.updated_at = utcnow().replace(microsecond=0)
        db.flush()
        return feedback_view(row)

    return run_operation(
        db,
        user_id,
        key,
        "recipe_feedback",
        {"recipe_id": str(recipe_id), **body.model_dump()},
        action,
    )


def cook(db, user_id, key, body, *, operation=None):
    def action(op):
        from .plans import validate_confirmation

        plan = validate_confirmation(db, user_id, body) if body.plan_id else None
        snapshot = recipe_view(db, user_id, body.recipe_id)
        if body.expected_recipe_version is not None and snapshot["version"] != body.expected_recipe_version:
            raise AppError(409, "VERSION_CONFLICT", "Recipe changed since cooking started")
        needed = required_quantities(snapshot, body.servings, body.include_optional)
        snapshot["include_optional"] = body.include_optional
        # Stable locking order across every write path; FEFO allocation follows after locks.
        batches = db.scalars(
            select(InventoryBatch)
            .where(
                InventoryBatch.user_id == user_id, InventoryBatch.ingredient_id.in_(sorted(needed))
            )
            .order_by(InventoryBatch.id)
            .with_for_update()
        ).all()
        usable = sorted(
            [b for b in batches if not b.archived and (b.expires_on is None or b.expires_on >= date.today())],
            key=lambda b: (b.expires_on or date.max, b.created_at, b.id),
        )
        consumption = []
        for ingredient_id, required in needed.items():
            remaining = required
            for batch in usable:
                if batch.ingredient_id != ingredient_id:
                    continue
                taken = min(batch.quantity, remaining)
                if taken > 0:
                    consumption.append((batch, taken))
                    remaining -= taken
            if remaining > 0:
                raise AppError(
                    409, "INSUFFICIENT_STOCK", "Not enough usable inventory; refresh the plan"
                )
        record = CookingRecord(user_id=user_id, recipe_snapshot=snapshot, servings=body.servings,
                               actual_minutes=body.actual_minutes, duration_source=body.duration_source)
        db.add(record)
        db.flush()
        for batch, taken in consumption:
            batch.quantity -= taken
            batch.version += 1
            db.add(
                CookingConsumption(
                    user_id=user_id, cooking_id=record.id, batch_id=batch.id, quantity=taken
                )
            )
            db.add(
                InventoryEvent(
                    user_id=user_id,
                    batch_id=batch.id,
                    operation_id=op.id,
                    delta=-taken,
                    reason="cooking",
                    batch_version=batch.version,
                )
            )
        if plan is not None:
            plan.status = "completed"
            plan.result = {"cooking_id": record.id, "version": plan.version}
        return {
            "id": record.id,
            "status": "completed",
            "recipe": snapshot,
            "servings": body.servings,
            "actual_minutes": record.actual_minutes,
            "duration_source": record.duration_source,
            "feedback_version": record.feedback_version,
        }

    if operation is not None:
        return action(operation)
    return run_operation(db, user_id, key, "cook", body.model_dump(mode="json"), action)


def update_duration(db, user_id, key, cooking_id, body):
    def action(op):
        record = owned(db, CookingRecord, cooking_id, user_id, lock=True)
        if record.status != "completed":
            raise AppError(409, "COOKING_RETRACTED", "Retracted cooking cannot be edited")
        if record.feedback_version != body.expected_version:
            raise AppError(409, "VERSION_CONFLICT", "Duration feedback changed")
        record.actual_minutes = body.actual_minutes
        record.duration_source = body.duration_source
        record.feedback_version += 1
        return {"id": record.id, "actual_minutes": record.actual_minutes,
                "duration_source": record.duration_source, "feedback_version": record.feedback_version}
    return run_operation(db, user_id, key, "cooking_duration",
                         {"cooking_id": str(cooking_id), **body.model_dump()}, action)


def undo(db, user_id, key, cooking_id, *, operation=None):
    def action(op):
        record = owned(db, CookingRecord, cooking_id, user_id, lock=True)
        if record.status == "retracted":
            return {"id": record.id, "status": "retracted"}
        lines = db.scalars(
            select(CookingConsumption)
            .where(
                CookingConsumption.cooking_id == record.id, CookingConsumption.user_id == user_id
            )
            .order_by(CookingConsumption.batch_id)
        ).all()
        for line in lines:
            batch = owned(db, InventoryBatch, line.batch_id, user_id, lock=True)
            batch.quantity += line.quantity
            if batch.quantity > Decimal("99999999999.999"):
                raise AppError(409, "QUANTITY_TOO_LARGE", "Restored quantity exceeds capacity")
            batch.version += 1
            db.add(
                InventoryEvent(
                    user_id=user_id,
                    batch_id=batch.id,
                    operation_id=op.id,
                    delta=line.quantity,
                    reason="undo",
                    batch_version=batch.version,
                )
            )
        record.status = "retracted"
        return {"id": record.id, "status": "retracted"}

    if operation is not None:
        return action(operation)
    return run_operation(db, user_id, key, "undo", {"cooking_id": str(cooking_id)}, action)


def set_staple(db, user_id, key, ingredient_id, body):
    def action(op):
        item = owned(db, Ingredient, ingredient_id, user_id, lock=True)
        item.is_staple = body.is_staple
        return {"id": item.id, "name": item.name, "unit": item.unit, "is_staple": item.is_staple}

    return run_operation(
        db,
        user_id,
        key,
        "set_staple",
        {"ingredient_id": str(ingredient_id), **body.model_dump()},
        action,
    )
