from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select

from ..models.food import CookingRecord, Ingredient, InventoryBatch, InventoryEvent, Recipe
from ..schemas.food import (
    AdjustmentInput,
    AliasInput,
    ArchiveInput,
    BatchInput,
    CookingInput,
    IngredientInput,
    RecipeFeedbackInput,
    RecipeInput,
    RecipeUpdateInput,
    StapleInput,
    UpdateDurationInput,
    VersionInput,
)
from ..services import food
from .pagination import Page
from .routes import get_db, get_identity

router = APIRouter(prefix="/api/v1")
Key = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
]


@router.get("/ingredients")
def ingredients(page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    return [
        {"id": i.id, "name": i.name, "unit": i.unit, "is_staple": i.is_staple}
        for i in db.scalars(
            select(Ingredient).where(Ingredient.user_id == current[0].id).order_by(Ingredient.name, Ingredient.id).limit(page.limit).offset(page.offset)
        )
    ]


@router.post("/ingredients", status_code=201)
def add_ingredient(body: IngredientInput, current=Depends(get_identity), db=Depends(get_db)):
    return food.add_ingredient(db, current[0].id, body)


@router.get("/ingredients/resolve")
def resolve(
    name: Annotated[str, Query(min_length=1, max_length=80)],
    current=Depends(get_identity),
    db=Depends(get_db),
):
    return food.resolve(db, current[0].id, name)


@router.post("/ingredients/{ingredient_id}/aliases", status_code=201)
def alias(ingredient_id: UUID, body: AliasInput, current=Depends(get_identity), db=Depends(get_db)):
    return food.add_alias(db, current[0].id, ingredient_id, body)


@router.get("/inventory")
def inventory(include_archived: bool = False, page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    return food.list_batches(db, current[0].id, include_archived, limit=page.limit, offset=page.offset)


@router.post("/inventory", status_code=201)
def add_batch(body: BatchInput, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    return food.add_batch(db, current[0].id, key, body)


@router.patch("/inventory/{batch_id}")
def adjust(
    batch_id: UUID,
    body: AdjustmentInput,
    key: Key,
    current=Depends(get_identity),
    db=Depends(get_db),
):
    return food.adjust_batch(db, current[0].id, key, batch_id, body)


@router.get("/inventory/events")
def events(page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    rows = db.scalars(
        select(InventoryEvent)
        .where(InventoryEvent.user_id == current[0].id)
        .order_by(InventoryEvent.created_at, InventoryEvent.batch_id,
                  InventoryEvent.batch_version, InventoryEvent.id).limit(page.limit).offset(page.offset)
    )
    return [
        {
            "id": e.id,
            "batch_id": e.batch_id,
            "delta": str(e.delta),
            "reason": e.reason,
            "batch_version": e.batch_version,
            "created_at": e.created_at,
        }
        for e in rows
    ]


@router.post("/recipes", status_code=201)
def add_recipe(body: RecipeInput, current=Depends(get_identity), db=Depends(get_db)):
    return food.add_recipe(db, current[0].id, body)


@router.get("/inventory/{batch_id}")
def batch(batch_id: UUID, current=Depends(get_identity), db=Depends(get_db)):
    row = food.owned(db, InventoryBatch, batch_id, current[0].id)
    return food.batch_view(row, food.owned(db, Ingredient, row.ingredient_id, current[0].id))


@router.post("/inventory/{batch_id}/archive")
def archive(batch_id: UUID, body: ArchiveInput, key: Key,
            current=Depends(get_identity), db=Depends(get_db)):
    return food.archive_batch(db, current[0].id, key, batch_id, body)


@router.put("/recipes/{recipe_id}")
def update_recipe(recipe_id: UUID, body: RecipeUpdateInput, key: Key,
                  current=Depends(get_identity), db=Depends(get_db)):
    return food.update_recipe(db, current[0].id, key, recipe_id, body)


@router.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: UUID, body: VersionInput, key: Key,
                  current=Depends(get_identity), db=Depends(get_db)):
    return food.delete_recipe(db, current[0].id, key, recipe_id, body)


@router.get("/recipes")
def recipes(page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    ids = db.scalars(
        select(Recipe.id).where(Recipe.user_id == current[0].id).order_by(Recipe.name, Recipe.id).limit(page.limit).offset(page.offset)
    ).all()
    views = [food.recipe_view(db, current[0].id, i) for i in ids]
    stored = food.feedback_map(db, current[0].id, list(ids))
    for view in views:
        view["feedback"] = stored.get(view["id"], food.empty_feedback(view["id"]))
    return views


@router.get("/recipes/{recipe_id}")
def recipe(recipe_id: UUID, current=Depends(get_identity), db=Depends(get_db)):
    view = food.recipe_view(db, current[0].id, recipe_id)
    view["feedback"] = food.get_feedback(db, current[0].id, recipe_id)
    return view


@router.get("/recipes/{recipe_id}/feedback")
def get_recipe_feedback(recipe_id: UUID, current=Depends(get_identity), db=Depends(get_db)):
    return food.get_feedback(db, current[0].id, recipe_id)


@router.put("/recipes/{recipe_id}/feedback")
def set_recipe_feedback(recipe_id: UUID, body: RecipeFeedbackInput, key: Key,
                        current=Depends(get_identity), db=Depends(get_db)):
    return food.set_feedback(db, current[0].id, key, recipe_id, body)


@router.post("/cooking", status_code=201)
def cook(body: CookingInput, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    return food.cook(db, current[0].id, key, body)


@router.post("/cooking/{cooking_id}/undo")
def undo(cooking_id: UUID, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    return food.undo(db, current[0].id, key, cooking_id)


@router.put("/cooking/{cooking_id}/duration")
def update_duration(cooking_id: UUID, body: UpdateDurationInput, key: Key,
                    current=Depends(get_identity), db=Depends(get_db)):
    return food.update_duration(db, current[0].id, key, cooking_id, body)


@router.get("/cooking")
def history(page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    rows = db.scalars(
        select(CookingRecord)
        .where(CookingRecord.user_id == current[0].id)
        .order_by(CookingRecord.created_at, CookingRecord.id).limit(page.limit).offset(page.offset)
    )
    return [
        {
            "id": c.id,
            "recipe": c.recipe_snapshot,
            "servings": c.servings,
            "status": c.status,
            "created_at": c.created_at,
            "actual_minutes": c.actual_minutes,
            "duration_source": c.duration_source,
            "feedback_version": c.feedback_version,
        }
        for c in rows
    ]


@router.patch("/ingredients/{ingredient_id}")
def mark_staple(
    ingredient_id: UUID,
    body: StapleInput,
    key: Key,
    current=Depends(get_identity),
    db=Depends(get_db),
):
    return food.set_staple(db, current[0].id, key, ingredient_id, body)


@router.post("/recipes/examples")
def install_examples(current=Depends(get_identity), db=Depends(get_db)):
    from ..services.examples import install

    return install(db, current[0].id)
