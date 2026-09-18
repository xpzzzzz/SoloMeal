from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .api.agent import router as agent_router
from .api.food import router as food_router
from .api.planning import router as planning_router
from .api.receipts import router as receipts_router
from .api.routes import router
from .api.run_events import router as run_events_router
from .api.shopping import router as shopping_router
from .core.config import Settings
from .core.database import build_engine, build_session_factory
from .core.errors import AppError
from .services.receipt_parser import VisionReceiptParser


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    engine = build_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title="SoloMeal", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = build_session_factory(engine)
    app.state.receipt_parser = VisionReceiptParser(settings)

    @app.exception_handler(AppError)
    async def application_error(request: Request, exc: AppError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message}},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Do not reflect raw credentials or other submitted input in errors.
        fields = [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
        return JSONResponse(
            status_code=422, content={"error": {"code": "VALIDATION_ERROR", "fields": fields}}
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        return JSONResponse(
            status_code=503,
            content={
                "error": {"code": "DATABASE_UNAVAILABLE", "message": "Database operation failed"}
            },
        )

    app.include_router(router)
    app.include_router(food_router)
    app.include_router(agent_router)
    app.include_router(run_events_router)
    app.include_router(planning_router)
    app.include_router(shopping_router)
    app.include_router(receipts_router)
    return app
