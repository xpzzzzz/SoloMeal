from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..models.proactivity import ProactiveSetting
from ..schemas.proactivity import (
    AcceptInput,
    AcceptResult,
    DismissInput,
    InboxOut,
    ItemResult,
    SettingsInput,
    SettingsOut,
    SimulateInput,
)
from ..services import proactivity_store
from ..services.food import run_operation
from ..services.home import shanghai_day
from .food import Key
from .routes import get_db, get_identity

router = APIRouter(prefix="/api/v1/proactivity")
Identity = Annotated[tuple, Depends(get_identity)]
Database = Annotated[Session, Depends(get_db)]


def now_for(request: Request, user_id: str) -> datetime:
    return request.app.state.proactivity_clock() + request.app.state.proactivity_offsets.get(user_id, 0) * request.app.state.proactivity_day


@router.get("/inbox", response_model=InboxOut)
def inbox(request: Request, current: Identity, db: Database):
    result = proactivity_store.inbox(db, current[0].id, now_for(request, current[0].id))
    result["meta"]["demo_mode"] = request.app.state.settings.demo_mode
    return result


@router.post("/items/{item_id}/dismiss", response_model=ItemResult)
def dismiss(item_id: UUID, body: DismissInput, key: Key, request: Request, current: Identity, db: Database):
    return proactivity_store.resolve_item(db, current[0].id, key, str(item_id), body,
                                          now_for(request, current[0].id), accept=False)


@router.post("/items/{item_id}/accept", response_model=AcceptResult)
def accept(item_id: UUID, body: AcceptInput, key: Key, request: Request, current: Identity, db: Database):
    return proactivity_store.resolve_item(db, current[0].id, key, str(item_id), body,
                                          now_for(request, current[0].id), accept=True)


@router.post("/items/{item_id}/complete", response_model=ItemResult)
def complete(item_id: UUID, key: Key, request: Request, current: Identity, db: Database):
    return proactivity_store.finish_action(db, current[0].id, key, str(item_id), now_for(request, current[0].id))


@router.post("/items/{item_id}/abandon", response_model=ItemResult)
def abandon(item_id: UUID, key: Key, request: Request, current: Identity, db: Database):
    return proactivity_store.finish_action(db, current[0].id, key, str(item_id),
                                           now_for(request, current[0].id), abandon=True)


@router.get("/settings", response_model=SettingsOut)
def settings(current: Identity, db: Database):
    return proactivity_store.settings_view(db.get(ProactiveSetting, current[0].id))


@router.patch("/settings", response_model=SettingsOut)
def change_settings(body: SettingsInput, key: Key, request: Request, current: Identity, db: Database):
    return proactivity_store.patch_settings(db, current[0].id, key, body, now_for(request, current[0].id))


def simulate(body: SimulateInput, key: Key, request: Request, current: Identity, db: Database):
    user_id = current[0].id
    # Serialize this process's demo offsets; replaying a key must never advance twice.
    with request.app.state.proactivity_offset_lock:
        offset = request.app.state.proactivity_offsets.get(user_id, 0)

        def action(_op):
            advanced = offset + body.days
            now = request.app.state.proactivity_clock() + advanced * request.app.state.proactivity_day
            counts = proactivity_store.tick_user(db, user_id, now, commit=False)
            return {"offset_days": advanced, "display_date": shanghai_day(now).isoformat(), **counts}

        result = run_operation(db, user_id, key, "proactive_simulate", body.model_dump(), action)
        request.app.state.proactivity_offsets[user_id] = max(offset, result["offset_days"])
        return {key: value for key, value in result.items() if key != "offset_days"}
