from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from ..schemas.discovery import (
    DiscoveryInput,
    DraftAcceptInput,
    DraftCreateInput,
    DraftEditInput,
    DraftValidateInput,
)
from ..schemas.food import VersionInput
from ..services import recipe_discovery as discovery
from .food import Key
from .pagination import Page
from .routes import get_db, get_identity

router = APIRouter(prefix="/api/v1")


@router.get("/recipe-discoveries/capabilities")
def capabilities(request: Request, current=Depends(get_identity)):
    return discovery.capabilities(request.app.state.settings)


@router.post("/recipe-discoveries", status_code=201)
async def start_discovery(request: Request, body: DiscoveryInput, key: Key,
                          current=Depends(get_identity), db=Depends(get_db)):
    return await discovery.start(db, current[0].id, key, body, request.app.state.settings,
                                 request.app.state.recipe_discovery)


@router.get("/recipe-discoveries")
def list_discoveries(page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    return discovery.list_batches(db, current[0].id, limit=page.limit, offset=page.offset)


@router.get("/recipe-discoveries/{batch_id}")
def discovery_detail(batch_id: UUID, current=Depends(get_identity), db=Depends(get_db)):
    return discovery.get_batch(db, current[0].id, batch_id)


@router.get("/recipe-drafts")
def list_drafts(batch_id: UUID | None = None,
                status: Literal["draft", "accepted", "discarded"] | None = None,
                page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    return discovery.list_drafts(db, current[0].id, batch_id=batch_id, status=status,
                                 limit=page.limit, offset=page.offset)


@router.post("/recipe-drafts", status_code=201)
def create_draft(body: DraftCreateInput, key: Key, current=Depends(get_identity),
                 db=Depends(get_db)):
    return discovery.create(db, current[0].id, key, body)


@router.get("/recipe-drafts/{draft_id}")
def draft_detail(draft_id: UUID, current=Depends(get_identity), db=Depends(get_db)):
    return discovery.get_draft(db, current[0].id, draft_id)


@router.put("/recipe-drafts/{draft_id}")
def edit_draft(draft_id: UUID, body: DraftEditInput, key: Key, current=Depends(get_identity),
               db=Depends(get_db)):
    return discovery.edit(db, current[0].id, key, draft_id, body)


@router.post("/recipe-drafts/{draft_id}/validate")
def validate_draft(draft_id: UUID, body: DraftValidateInput, current=Depends(get_identity),
                   db=Depends(get_db)):
    return discovery.check(db, current[0].id, draft_id, body)


@router.post("/recipe-drafts/{draft_id}/accept")
def accept_draft(draft_id: UUID, body: DraftAcceptInput, key: Key, current=Depends(get_identity),
                 db=Depends(get_db)):
    return discovery.accept(db, current[0].id, key, draft_id, body)


@router.post("/recipe-drafts/{draft_id}/discard")
def discard_draft(draft_id: UUID, body: VersionInput, key: Key,
                  current=Depends(get_identity), db=Depends(get_db)):
    return discovery.discard(db, current[0].id, key, draft_id, body)
