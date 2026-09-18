from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from ..models.agent import AgentRun, AgentSession
from ..schemas.agent import RunInput
from ..services import agent, food
from ..services.agent_model import ChatModel
from .food import Key
from .pagination import Page
from .routes import get_db, get_identity

router = APIRouter(prefix="/api/v1/agent")


@router.get("/sessions")
def sessions(page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    return [agent.session_view(db, s) for s in db.scalars(select(AgentSession).where(
        AgentSession.user_id == current[0].id).order_by(AgentSession.id).limit(page.limit).offset(page.offset))]


@router.get("/sessions/{session_id}")
def session(session_id: UUID, current=Depends(get_identity), db=Depends(get_db)):
    return agent.session_view(db, food.owned(db, AgentSession, session_id, current[0].id))


@router.post("/runs", status_code=201)
def create(body: RunInput, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    return agent.create(db, current[0].id, key, body)


@router.get("/runs")
def listing(page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    return [
        {"id": r.id, "status": r.status, "steps": r.steps}
        for r in db.scalars(
            select(AgentRun).where(AgentRun.user_id == current[0].id).order_by(AgentRun.id).limit(page.limit).offset(page.offset)
        )
    ]


@router.get("/runs/{run_id}")
def get(run_id: UUID, current=Depends(get_identity), db=Depends(get_db)):
    return agent.view(db, food.owned(db, AgentRun, run_id, current[0].id))


@router.post("/runs/{run_id}/advance")
def advance(run_id: UUID, request: Request, current=Depends(get_identity), db=Depends(get_db)):
    model = getattr(request.app.state, "agent_model", None) or ChatModel(request.app.state.settings)
    return agent.advance(db, current[0].id, run_id, model)


@router.post("/runs/{run_id}/{action}")
def transition(
    run_id: UUID, action: str, key: Key, current=Depends(get_identity), db=Depends(get_db)
):
    from ..core.errors import AppError

    if action not in ("approve", "cancel", "retry"):
        raise AppError(404, "NOT_FOUND", "Unknown action")
    return agent.transition(db, current[0].id, key, run_id, action)
