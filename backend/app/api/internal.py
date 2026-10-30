import hmac
from typing import Annotated

from fastapi import APIRouter, Header, Request

from ..core.errors import AppError
from ..schemas.proactivity import TickInput, TickResult
from ..services.proactivity_store import tick_all
from .proactivity import Database

router = APIRouter(prefix="/internal")


@router.post("/tick", response_model=TickResult)
def tick(body: TickInput, request: Request, db: Database,
         token: Annotated[str | None, Header(alias="X-Internal-Token")] = None):
    configured = request.app.state.settings.tick_token
    if configured is None or not configured.get_secret_value():
        raise AppError(404, "NOT_FOUND", "Not found")
    if token is None or not hmac.compare_digest(token, configured.get_secret_value()):
        raise AppError(401, "UNAUTHENTICATED", "Invalid internal token")
    return tick_all(db, request.app.state.proactivity_clock(), body.user_id, request.app.state.proactivity_offsets)
