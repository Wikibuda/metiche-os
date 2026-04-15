from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.core.db import get_session
from app.services.dashboard_service import (
    get_channel_events,
    get_channels_status,
    get_dashboard_stats,
    get_whatsapp_conversations,
    get_recent_narratives_block,
    get_task_detail,
    get_validator_statuses,
    list_dashboard_tasks,
    perform_task_action,
    run_quick_task,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
_ROOT_DIR = Path(__file__).resolve().parents[2]
_OPERATIVO_HTML = _ROOT_DIR / "dashboard" / "operativo.html"
_ADMIN_DASHBOARD_HTML = _ROOT_DIR / "dashboard" / "admin-dashboard-lab.html"


class QuickTaskRequest(BaseModel):
    channel: str
    title: str
    description: str | None = None
    launch_swarm: bool = False


class TaskActionRequest(BaseModel):
    action: str
    priority: str | None = None


@router.get("/operativo")
def get_operativo_html() -> FileResponse:
    if not _OPERATIVO_HTML.exists():
        raise HTTPException(status_code=404, detail="dashboard/operativo.html no existe")
    return FileResponse(_OPERATIVO_HTML)


@router.get("/admin-dashboard")
@router.get("/admin-dashboard.html")
@router.get("/swarm-console")
@router.get("/swarm-console.html")
def get_admin_dashboard_html() -> FileResponse:
    if not _ADMIN_DASHBOARD_HTML.exists():
        raise HTTPException(status_code=404, detail="dashboard/admin-dashboard-lab.html no existe")
    return FileResponse(_ADMIN_DASHBOARD_HTML)


@router.get("/stats")
def get_dashboard_stats_route(
    retrying_threshold_minutes: int = Query(default=2, ge=1, le=60),
    blocking_threshold: int = Query(default=3, ge=1, le=50),
    session: Session = Depends(get_session),
) -> dict:
    return get_dashboard_stats(
        session,
        retrying_threshold_minutes=retrying_threshold_minutes,
        blocking_threshold=blocking_threshold,
    )


@router.get("/tasks")
def get_dashboard_tasks_route(
    channel: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    q: str | None = None,
    limit: int = Query(default=120, ge=1, le=400),
    session: Session = Depends(get_session),
) -> dict:
    return list_dashboard_tasks(
        session,
        channel=channel,
        status=status,
        priority=priority,
        task_id_query=q,
        limit=limit,
    )


@router.get("/tasks/{task_id}")
def get_dashboard_task_detail_route(task_id: str, session: Session = Depends(get_session)) -> dict:
    detail = get_task_detail(session, task_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return detail


@router.post("/tasks/run")
def run_dashboard_task_route(payload: QuickTaskRequest, session: Session = Depends(get_session)) -> dict:
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="El titulo es obligatorio")
    return run_quick_task(
        session,
        channel=payload.channel,
        title=payload.title,
        description=payload.description,
        launch_swarm=payload.launch_swarm,
    )


@router.post("/tasks/{task_id}/action")
def dashboard_task_action_route(task_id: str, payload: TaskActionRequest, session: Session = Depends(get_session)) -> dict:
    try:
        return perform_task_action(session, task_id=task_id, action=payload.action, priority=payload.priority)
    except ValueError as exc:
        code = str(exc)
        if code == "task_not_found":
            raise HTTPException(status_code=404, detail="Tarea no encontrada") from exc
        if code == "queued_entry_not_found":
            raise HTTPException(status_code=409, detail="La tarea no tiene entrada en cola para editar prioridad") from exc
        raise HTTPException(status_code=400, detail="Accion no soportada") from exc


@router.get("/validators")
def get_dashboard_validators_route(session: Session = Depends(get_session)) -> dict:
    return {"generated_at": datetime.utcnow(), "items": get_validator_statuses(session)}


@router.get("/recent-narratives")
def get_dashboard_recent_narratives_route(
    limit: int = Query(default=8, ge=1, le=20),
    session: Session = Depends(get_session),
) -> dict:
    return {"generated_at": datetime.utcnow(), "items": get_recent_narratives_block(session, limit=limit)}


@router.get("/channels/status")
def get_dashboard_channels_status_route(
    event_preview_limit: int = Query(default=5, ge=1, le=10),
    inactivity_minutes: int = Query(default=1440, ge=1, le=1440),
    session: Session = Depends(get_session),
) -> dict:
    return get_channels_status(
        session,
        event_preview_limit=event_preview_limit,
        inactivity_minutes=inactivity_minutes,
    )


@router.get("/channels/events")
def get_dashboard_channel_events_route(
    channel: str = Query(..., description="Canal a consultar: whatsapp|telegram"),
    limit: int = Query(default=10, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict:
    try:
        return get_channel_events(session, channel=channel, limit=limit)
    except ValueError as exc:
        if str(exc) == "unsupported_channel":
            raise HTTPException(status_code=400, detail="Canal no soportado") from exc
        raise


@router.get("/conversations")
def get_dashboard_conversations_route(
    q: str | None = Query(default=None, description="Busqueda por client_key o texto"),
    limit_clients: int = Query(default=20, ge=1, le=100),
    limit_messages: int = Query(default=40, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    return get_whatsapp_conversations(
        session,
        q=q,
        limit_clients=limit_clients,
        limit_messages_per_client=limit_messages,
    )
