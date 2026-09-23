from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..core.errors import AppError
from ..services import home
from .routes import get_db, get_identity

router = APIRouter(prefix="/api/v1")


@router.get("/home")
def aggregate(sections: Annotated[str | None, Query(max_length=120)] = None,
              current=Depends(get_identity), db=Depends(get_db)):
    return home.build(db, current[0].id, home.selected(sections))


@router.get("/home/{section}")
def one_section(section: str, current=Depends(get_identity), db=Depends(get_db)):
    result = home.build_section(db, current[0].id, section)
    if result is None:
        raise AppError(404, "NOT_FOUND", "Unknown home section")
    return result
