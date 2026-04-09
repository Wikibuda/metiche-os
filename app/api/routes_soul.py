from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.db import get_session
from app.domain.soul.service import get_metiche_soul

router = APIRouter(prefix="/soul", tags=["soul"])


@router.get("/metiche")
def get_metiche_soul_route(session: Session = Depends(get_session)) -> dict:
    return get_metiche_soul(session)
