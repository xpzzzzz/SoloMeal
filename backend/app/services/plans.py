from datetime import date

from sqlalchemy import select

from ..core.errors import AppError
from ..models.food import InventoryBatch
from ..models.identity import UserPreference
from ..models.plans import MealPlan, PlanRevision
from ..schemas.planning import PlanningInput
from .food import owned, recipe_view, run_operation
from .planning import freeze_quotes, quote_snapshot, recommend


def state(db, user_id, recipe):
    ids = [i["ingredient_id"] for i in recipe["ingredients"]]
    rows = db.scalars(
        select(InventoryBatch)
        .where(InventoryBatch.user_id == user_id, InventoryBatch.ingredient_id.in_(ids))
        .order_by(InventoryBatch.id)
    ).all()
    preference = db.get(UserPreference, user_id, populate_existing=True)
    return {
        "date": date.today().isoformat(),
        "batches": [
            {
                "id": b.id,
                "version": b.version,
                "quantity": str(b.quantity),
                "archived": b.archived,
                "expires_on": b.expires_on.isoformat() if b.expires_on else None,
            }
            for b in rows
        ],
        "preferences": {
            "equipment": preference.equipment,
            "excluded_ingredients": preference.excluded_ingredients,
            "default_servings": preference.default_servings,
            "max_minutes": preference.max_minutes,
        },
        "recipe": recipe,
    }


def revision(db, plan):
    return db.scalar(
        select(PlanRevision).where(
            PlanRevision.plan_id == plan.id,
            PlanRevision.user_id == plan.user_id,
            PlanRevision.version == plan.version,
        )
    )


def history(db, user_id, plan_id, *, limit=None, offset=0):
    plan = owned(db, MealPlan, plan_id, user_id)
    return [{"version": row.version, "snapshot": row.snapshot} for row in db.scalars(
        select(PlanRevision).where(PlanRevision.plan_id == plan.id,
                                   PlanRevision.user_id == user_id).order_by(PlanRevision.version).limit(limit).offset(offset)
    )]


def cancel(db, user_id, key, plan_id, body):
    def action(op):
        plan = owned(db, MealPlan, plan_id, user_id, lock=True)
        if plan.version != body.expected_version or plan.status != "pending":
            raise AppError(409, "PLAN_CONFLICT", "Plan is not pending at this version")
        plan.status = "cancelled"
        return view(db, plan)

    return run_operation(db, user_id, key, "cancel_plan",
                         {"plan_id": str(plan_id), **body.model_dump()}, action)


def view(db, plan):
    return {
        "id": plan.id,
        "version": plan.version,
        "status": plan.status,
        "snapshot": revision(db, plan).snapshot,
        "result": plan.result,
    }


def save(db, user_id, key, body, plan_id=None, *, within_operation=False):
    def action(op):
        if plan_id:
            plan = owned(db, MealPlan, plan_id, user_id, lock=True)
            if plan.status != "pending" or plan.version != body.expected_version:
                raise AppError(409, "PLAN_CONFLICT", "Plan is no longer editable at this version")
            plan.version += 1
        else:
            plan = MealPlan(user_id=user_id, version=1)
            db.add(plan)
            db.flush()
        constraints = freeze_quotes(db, user_id, body.constraints)
        result = recommend(db, user_id, constraints)
        candidate = next(
            (c for c in result["candidates"] if c["recipe"]["id"] == str(body.recipe_id)), None
        )
        if candidate is None:
            raise AppError(409, "PLAN_INFEASIBLE", "Recipe does not satisfy current constraints")
        snapshot = {
            "request": quote_snapshot(constraints, candidate["recipe"]).model_dump(mode="json"),
            "constraints": result["constraints"],
            "candidate": candidate,
            "state": state(db, user_id, candidate["recipe"]),
        }
        db.add(
            PlanRevision(plan_id=plan.id, user_id=user_id, version=plan.version, snapshot=snapshot)
        )
        db.flush()
        return view(db, plan)

    if within_operation:
        return action(None)
    return run_operation(
        db,
        user_id,
        key,
        "revise_plan" if plan_id else "create_plan",
        {"plan_id": str(plan_id) if plan_id else None, **body.model_dump(mode="json")},
        action,
    )


def validate_confirmation(db, user_id, body):
    plan = owned(db, MealPlan, body.plan_id, user_id, lock=True)
    if plan.version != body.expected_plan_version or plan.status != "pending":
        raise AppError(409, "PLAN_CONFLICT", "Plan is not pending at this version")
    snapshot = revision(db, plan).snapshot
    candidate = snapshot["candidate"]
    if str(body.recipe_id) != candidate["recipe"]["id"] or body.servings != candidate["servings"]:
        raise AppError(409, "PLAN_CONFLICT", "Cooking parameters do not match confirmed plan")
    if body.include_optional != candidate.get("include_optional", False):
        raise AppError(409, "PLAN_CONFLICT", "Optional ingredient choice differs from plan")
    try:
        current_recipe = recipe_view(db, user_id, body.recipe_id)
    except AppError as exc:
        if exc.code == "NOT_FOUND":
            raise AppError(409, "PLAN_STALE", "Recipe was deleted; create a new plan") from exc
        raise
    if snapshot["state"] != state(db, user_id, current_recipe):
        raise AppError(
            409, "PLAN_STALE", "Inventory, recipe, date or preferences changed; revise plan"
        )
    current = recommend(db, user_id, PlanningInput.model_validate(
        {"use_saved_quotes": False, **snapshot["request"]}))
    if not any(c["recipe"]["id"] == str(body.recipe_id) for c in current["candidates"]):
        raise AppError(409, "PLAN_STALE", "Current constraints no longer permit this recipe")
    if candidate["budget_status"] == "unknown":
        raise AppError(
            409, "BUDGET_UNKNOWN", "Budget cannot be verified; revise constraints or prices"
        )
    return plan
