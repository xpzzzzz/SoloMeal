from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select

from ..models.shopping import SavedQuote, ShoppingList
from ..schemas.food import VersionInput
from ..schemas.shopping import (
    CombinedCreateInput,
    CombinedPreviewInput,
    SaveQuoteInput,
    ShoppingCheckedInput,
    ShoppingCreateInput,
    ShoppingEditInput,
)
from ..services import combined_shopping, shopping
from ..services.food import owned
from .food import Key
from .pagination import Page
from .routes import get_db, get_identity

router = APIRouter(prefix="/api/v1")


@router.get("/quotes")
def quotes(page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    return [shopping.quote_view(db, row) for row in db.scalars(select(SavedQuote).where(
        SavedQuote.user_id == current[0].id).order_by(SavedQuote.ingredient_id).limit(page.limit).offset(page.offset))]


@router.post("/quotes")
def save_quote(body: SaveQuoteInput, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    return shopping.save_quote(db, current[0].id, key, body)


@router.get("/shopping")
def lists(page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    return [shopping.view(row) for row in db.scalars(select(ShoppingList).where(
        ShoppingList.user_id == current[0].id).order_by(ShoppingList.created_at, ShoppingList.id).limit(page.limit).offset(page.offset))]


@router.post("/shopping/combined-preview")
def combined_preview(body: CombinedPreviewInput, current=Depends(get_identity), db=Depends(get_db)):
    return combined_shopping.preview(db, current[0].id, body)


@router.post("/shopping/combined", status_code=201)
def combined_create(body: CombinedCreateInput, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    return combined_shopping.create(db, current[0].id, key, body)


@router.post("/shopping/{list_id}/check")
def check(list_id: UUID, body: ShoppingCheckedInput, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    return shopping.change(db, current[0].id, key, list_id, body, "check")


@router.post("/shopping/{list_id}/close")
def close(list_id: UUID, body: VersionInput, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    return shopping.change(db, current[0].id, key, list_id, body, "close")


@router.get("/shopping/{list_id}")
def get_list(list_id: UUID, current=Depends(get_identity), db=Depends(get_db)):
    return shopping.view(owned(db, ShoppingList, list_id, current[0].id))


@router.post("/shopping", status_code=201)
def create(body: ShoppingCreateInput, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    return shopping.create(db, current[0].id, key, body)


@router.post("/shopping/{list_id}/edit")
def edit(list_id: UUID, body: ShoppingEditInput, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    return shopping.change(db, current[0].id, key, list_id, body, "edit")


@router.post("/shopping/{list_id}/confirm")
def confirm(list_id: UUID, body: VersionInput, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    return shopping.change(db, current[0].id, key, list_id, body, "confirm")


@router.post("/shopping/{list_id}/cancel")
def cancel(list_id: UUID, body: VersionInput, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    return shopping.change(db, current[0].id, key, list_id, body, "cancel")
