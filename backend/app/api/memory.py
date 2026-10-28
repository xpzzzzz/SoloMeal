from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..schemas.memory import ConfirmMemoryInput, MemoryInput
from ..services import memory_operations
from ..services.memory import MemoryPreference, MemoryReadError
from .routes import get_db, get_identity

router = APIRouter(prefix="/api/v1/me/memories")
CurrentIdentity = Annotated[tuple, Depends(get_identity)]
CurrentDb = Annotated[Session, Depends(get_db)]


def _preference(body: MemoryInput) -> MemoryPreference:
    return MemoryPreference(category=body.category, target=body.target, polarity=body.polarity)


@router.get("")
def list_memories(request: Request, response: Response, current: CurrentIdentity):
    response.headers["Cache-Control"] = "no-store"
    try:
        items = request.app.state.memory_provider.list_for_management(current[0].id)
    except MemoryReadError as exc:
        code = {"unavailable": "MEMORY_UNAVAILABLE", "incomplete": "MEMORY_INCOMPLETE",
                "unverified": "MEMORY_OWNERSHIP_UNVERIFIED"}.get(exc.reason, "MEMORY_UNAVAILABLE")
        raise AppError(503, code, "Memory list could not be verified") from exc
    except Exception as exc:
        # Never reflect provider diagnostics, credentials or raw preferences.
        raise AppError(503, "MEMORY_UNAVAILABLE", "Memory list is unavailable") from exc
    if items is None:
        raise AppError(503, "MEMORY_UNAVAILABLE", "Memory list is unavailable")
    return [asdict(item) for item in items]


@router.post("/confirm")
def confirm_memory(body: ConfirmMemoryInput, request: Request, current: CurrentIdentity, db: CurrentDb):
    return memory_operations.confirm(db, current[0].id, str(body.run_id), body.step,
                                     _preference(body), request.app.state.memory_provider)


@router.put("/{memory_id}")
def update_memory(memory_id: str, body: MemoryInput, request: Request, current: CurrentIdentity, db: CurrentDb):
    if len(memory_id) > 128:
        raise AppError(422, "VALIDATION_ERROR", "Invalid memory ID")
    return memory_operations.update(db, current[0].id, memory_id, _preference(body), request.app.state.memory_provider)


@router.delete("/{memory_id}")
def delete_memory(memory_id: str, request: Request, current: CurrentIdentity, db: CurrentDb):
    if len(memory_id) > 128:
        raise AppError(422, "VALIDATION_ERROR", "Invalid memory ID")
    return memory_operations.delete(db, current[0].id, memory_id, request.app.state.memory_provider)
