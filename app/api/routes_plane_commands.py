from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.db import get_session
from app.services.plane_comment_watcher import list_plane_command_history

router = APIRouter(prefix="/api/plane-commands", tags=["plane-commands"])


@router.get("/history")
def get_plane_commands_history(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    return {
        "limit": limit,
        "items": list_plane_command_history(session, limit=limit),
    }
