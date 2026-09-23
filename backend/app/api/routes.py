from pathlib import Path
from typing import Annotated

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..core.errors import AppError
from ..schemas.identity import Credentials, Preferences, SessionView, UserView
from ..services import identity, personalization

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def get_db(request: Request):
    with request.app.state.sessions() as db:
        yield db


def get_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db=Depends(get_db),
):
    if credentials is None:
        raise AppError(401, "UNAUTHENTICATED", "A valid session is required")
    return identity.authenticate(db, credentials.credentials)


@router.get("/health/live")
def live():
    return {"status": "ok", "service": "solomeal"}


@router.get("/health/ready")
def ready(db=Depends(get_db)):
    try:
        actual = db.scalars(text("SELECT version_num FROM alembic_version")).all()
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        expected = ScriptDirectory.from_config(config).get_heads()
        if sorted(actual) != sorted(expected):
            raise AppError(503, "MIGRATIONS_PENDING", "Database migrations are pending")
    except SQLAlchemyError as exc:
        raise AppError(503, "DATABASE_NOT_READY", "Database or migrations are not ready") from exc
    return {"status": "ready"}


@router.post("/api/v1/auth/register", response_model=UserView, status_code=201)
def register(body: Credentials, db=Depends(get_db)):
    return identity.register(db, body)


@router.post("/api/v1/auth/login", response_model=SessionView)
def login(body: Credentials, request: Request, response: Response, db=Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return identity.login(db, body, request.app.state.settings.session_ttl_seconds)


@router.post("/api/v1/auth/logout", status_code=204)
def logout(current=Depends(get_identity), db=Depends(get_db)):
    _, session = current
    db.delete(session)
    db.commit()


@router.get("/api/v1/me", response_model=UserView)
def me(current=Depends(get_identity)):
    return current[0]


@router.get("/api/v1/me/preferences", response_model=Preferences)
def preferences(current=Depends(get_identity), db=Depends(get_db)):
    return identity.get_preferences(db, current[0].id)


@router.put("/api/v1/me/preferences", response_model=Preferences)
def set_preferences(body: Preferences, current=Depends(get_identity), db=Depends(get_db)):
    return identity.update_preferences(db, current[0].id, body)


@router.get("/api/v1/me/personalization")
def personalization_summary(current=Depends(get_identity), db=Depends(get_db)):
    preferences = identity.get_preferences(db, current[0].id)
    return personalization.summary(db, current[0].id, enabled=bool(preferences.personalization_enabled))
