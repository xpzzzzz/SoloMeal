from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select

from ..models.plans import MealPlan
from ..schemas.food import CookingInput
from ..schemas.planning import ConfirmPlanInput, PlanInput, PlanningInput, RevisePlanInput
from ..services import food, plans
from ..services.planning import recommend
from .food import Key
from .pagination import Page
from .routes import get_db, get_identity

router = APIRouter(prefix="/api/v1")


@router.post("/recommendations")
def recommendations(body: PlanningInput, current=Depends(get_identity), db=Depends(get_db)):
    return recommend(db, current[0].id, body)


@router.post("/plans", status_code=201)
def create_plan(body: PlanInput, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    return plans.save(db, current[0].id, key, body)


@router.get("/plans")
def list_plans(page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    return [
        plans.view(db, p)
        for p in db.scalars(
            select(MealPlan).where(MealPlan.user_id == current[0].id).order_by(MealPlan.id).limit(page.limit).offset(page.offset)
        )
    ]


@router.get("/plans/{plan_id}")
def get_plan(plan_id: UUID, current=Depends(get_identity), db=Depends(get_db)):
    return plans.view(db, food.owned(db, MealPlan, plan_id, current[0].id))


@router.post("/plans/{plan_id}/revisions")
def revise_plan(
    plan_id: UUID,
    body: RevisePlanInput,
    key: Key,
    current=Depends(get_identity),
    db=Depends(get_db),
):
    return plans.save(db, current[0].id, key, body, plan_id)


@router.post("/plans/{plan_id}/confirm")
def confirm_plan(
    plan_id: UUID,
    body: ConfirmPlanInput,
    key: Key,
    current=Depends(get_identity),
    db=Depends(get_db),
):
    plan = food.owned(db, MealPlan, plan_id, current[0].id)
    # The transaction validator repeats all checks under the owner lock.
    candidate = plans.revision(db, plan).snapshot["candidate"]
    request = CookingInput(
        recipe_id=candidate["recipe"]["id"],
        servings=candidate["servings"],
        plan_id=plan_id,
        expected_plan_version=body.expected_version,
        actual_minutes=body.actual_minutes,
        duration_source=body.duration_source,
        include_optional=candidate.get("include_optional", False),
    )
    return food.cook(db, current[0].id, key, request)


@router.get("/plans/{plan_id}/revisions")
def plan_history(plan_id: UUID, page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    return plans.history(db, current[0].id, plan_id, limit=page.limit, offset=page.offset)


@router.post("/plans/{plan_id}/cancel")
def cancel_plan(plan_id: UUID, body: ConfirmPlanInput, key: Key,
                current=Depends(get_identity), db=Depends(get_db)):
    return plans.cancel(db, current[0].id, key, plan_id, body)
