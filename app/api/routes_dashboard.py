from datetime import datetime
from pathlib import Path

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.core.db import get_session
from app.domain.swarm.models import SwarmCreate
from app.domain.swarm.service import create_swarm
from app.domain.tasks.models import TaskEnqueueCreate
from app.services.dashboard_service import (
    get_channel_events,
    get_channels_status,
    get_dashboard_stats,
    get_plane_issues_section,
    get_whatsapp_conversations,
    get_recent_narratives_block,
    get_task_detail,
    get_validator_statuses,
    list_dashboard_tasks,
    perform_task_action,
    run_quick_task,
)
from app.services.fifo_queue import (
    can_enqueue,
    enqueue_fifo as fifo_enqueue,
    get_queue_full,
    process_next as fifo_process_next,
    get_queue_length,
    PRIORITY_LEVELS,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
_ROOT_DIR = Path(__file__).resolve().parents[2]
_OPERATIVO_HTML = _ROOT_DIR / "dashboard" / "operativo.html"
_ADMIN_DASHBOARD_HTML = _ROOT_DIR / "dashboard" / "admin-dashboard-lab.html"
_TRAJE_IRON_MAN_HTML = _ROOT_DIR / "dashboard" / "traje-iron-man.html"
class QuickTaskRequest(BaseModel):
    channel: str
    title: str
    description: str | None = None
    launch_swarm: bool = False


class TaskActionRequest(BaseModel):
    action: str
    priority: str | None = None


class CreateIssueRequest(BaseModel):
    title: str
    description: str | None = None
    priority: str = "high"
    launch_swarm: bool = False


class RunSwarmRequest(BaseModel):
    title: str
    goal: str


class FIFOEnqueueRequest(BaseModel):
    title: str
    description: str | None = None
    priority: str = "medium"
    task_type: str = "operational"


@router.get("/operativo")
def get_operativo_html() -> FileResponse:
    if not _OPERATIVO_HTML.exists():
        raise HTTPException(status_code=404, detail="dashboard/operativo.html no existe")
    return FileResponse(_OPERATIVO_HTML)


@router.get("/traje-iron-man")
@router.get("/traje-iron-man.html")
def get_traje_iron_man_html() -> FileResponse:
    if not _TRAJE_IRON_MAN_HTML.exists():
        raise HTTPException(status_code=404, detail="dashboard/traje-iron-man.html no existe")
    return FileResponse(_TRAJE_IRON_MAN_HTML)


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


@router.get("/plane/issues")
def get_dashboard_plane_issues_route(
    limit: int = Query(default=30, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    return get_plane_issues_section(session, limit=limit)


@router.get("/conversations")
def get_dashboard_conversations_route(
    q: str | None = Query(default=None, description="Busqueda por client_key o texto"),
    phone: str | None = Query(default=None, description="Filtro por telefono/client_key"),
    customer_name: str | None = Query(default=None, description="Filtro por nombre de cliente"),
    date_from: str | None = Query(default=None, description="Fecha inicial YYYY-MM-DD"),
    date_to: str | None = Query(default=None, description="Fecha final YYYY-MM-DD"),
    limit_clients: int = Query(default=20, ge=1, le=100),
    limit_messages: int = Query(default=40, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    return get_whatsapp_conversations(
        session,
        q=q,
        phone=phone,
        customer_name=customer_name,
        date_from=date_from,
        date_to=date_to,
        limit_clients=limit_clients,
        limit_messages_per_client=limit_messages,
    )


# ── FIFO Queue Endpoints ────────────────────────────────────────────────


@router.get("/fifo-queue")
def get_fifo_queue_route(session: Session = Depends(get_session)) -> dict:
    """
    Retorna el estado completo de la cola FIFO:
    total, lengths (por nivel), grouped (entries agrupadas por nivel).
    """
    return get_queue_full(session)


@router.get("/fifo-queue/lengths")
def get_fifo_queue_lengths_route(
    priority: str | None = Query(default=None, description="Filtrar por nivel"),
    session: Session = Depends(get_session),
) -> dict:
    """Retorna las longitudes de la cola por nivel de prioridad."""
    if priority and not can_enqueue(session, priority):
        raise HTTPException(
            status_code=400,
            detail=f"Prioridad invalida. Valores: {', '.join(PRIORITY_LEVELS)}",
        )
    return {"generated_at": datetime.utcnow(), "lengths": get_queue_length(session, priority)}


@router.post("/fifo-queue/enqueue")
def fifo_enqueue_route(
    payload: FIFOEnqueueRequest,
    session: Session = Depends(get_session),
) -> dict:
    """
    Encola una tarea en la cola FIFO con la prioridad indicada.
    """
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="El titulo es obligatorio")

    try:
        task_payload = TaskEnqueueCreate(
            title=payload.title.strip(),
            description=payload.description,
            priority=payload.priority,
            task_type=payload.task_type,
        )
        entry = fifo_enqueue(session, task_payload, priority=payload.priority)
        return {
            "ok": True,
            "queue_entry": entry.model_dump(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fifo-queue/process-next")
def fifo_process_next_route(session: Session = Depends(get_session)) -> dict:
    """
    Extrae la siguiente tarea de la cola (por orden de prioridad) y la procesa.
    Retorna la tarea o un mensaje de cola vacia.
    """
    result = fifo_process_next(session)
    if result is None:
        return {"ok": False, "message": "La cola esta vacia"}
    return {"ok": True, **result}


@router.post("/fifo-queue/clear")
def fifo_clear_route(session: Session = Depends(get_session)) -> dict:
    """
    Cancela TODAS las tareas encoladas (limpia la cola).
    """
    from sqlalchemy import text as sql_text

    now = datetime.utcnow()
    conn = session.connection()
    try:
        conn.execute(
            sql_text(
                "UPDATE queueentry SET status = 'cancelled', completed_at = :now "
                "WHERE status = 'queued'"
            ),
            {"now": now},
        )
        conn.execute(
            sql_text(
                "UPDATE task SET status = 'cancelled', updated_at = :now "
                "WHERE status IN ('queued', 'new')"
            ),
            {"now": now},
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Error al vaciar cola: {exc}") from exc

    return {"ok": True, "message": "Cola vaciada", "cleared_at": now.isoformat()}


# ── Plane Actions Endpoints ─────────────────────────────────────────────


@router.post("/create-issue")
def create_issue_route(
    payload: CreateIssueRequest,
    session: Session = Depends(get_session),
) -> dict:
    """
    Crea un issue en Plane (via la integracion) y opcionalmente
    dispara un enjambre.
    """
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="El titulo es obligatorio")

    # Intentar crear el issue en Plane y/o encolar la tarea
    issue_id = str(uuid4())[:13]
    issue_url = None

    try:
        from app.integrations.plane import create_issue as plane_create_issue

        labels = [f"priority:{payload.priority}"]
        if payload.launch_swarm:
            labels.append("run:enjambre")

        description = payload.description or ""
        if payload.launch_swarm:
            description += "\n\n[auto: lanzar enjambre al procesar]"

        plane_resp = plane_create_issue(
            title=payload.title,
            description_html=description,
            labels=labels,
        )
        if plane_resp.ok:
            if isinstance(plane_resp.data, dict):
                issue_id = plane_resp.data.get("id") or plane_resp.data.get("identifier") or issue_id
                issue_url = plane_resp.data.get("url") or None
    except Exception:
        # Fallback: encolar como tarea local si Plane falla
        pass

    # Encolar como tarea local
    task_type = "enjambre" if payload.launch_swarm else "operational"
    try:
        task_payload = TaskEnqueueCreate(
            title=payload.title.strip(),
            description=payload.description,
            priority=payload.priority,
            task_type=task_type,
        )
        entry = fifo_enqueue(session, task_payload, priority=payload.priority)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "ok": True,
        "issue_id": issue_id,
        "issue_url": issue_url,
        "queue_entry": entry.model_dump(),
        "launch_swarm": payload.launch_swarm,
    }


@router.post("/run-swarm")
def run_swarm_route(
    payload: RunSwarmRequest,
    session: Session = Depends(get_session),
) -> dict:
    """
    Crea y lanza un enjambre (swarm) desde el Dashboard.
    """
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="El titulo es obligatorio")
    if not payload.goal.strip():
        raise HTTPException(status_code=400, detail="El objetivo del enjambre es obligatorio")

    try:
        swarm_payload = SwarmCreate(
            name=payload.title.strip(),
            goal=payload.goal.strip(),
            policy="narrative-consensus",
            agents=["whatsapp", "telegram", "deepseek"],
        )
        swarm = create_swarm(session, swarm_payload)
        return {
            "ok": True,
            "swarm_id": swarm.id,
            "swarm_name": swarm.name,
            "goal": swarm.goal,
            "status": swarm.status,
            "agents": [agent.agent_name for agent in swarm.agents],
        }
    except ValueError as exc:
        detail = str(exc)
        if detail == "invalid_policy":
            raise HTTPException(status_code=400, detail="Policy no valida") from exc
        if detail == "empty_agents":
            raise HTTPException(status_code=400, detail="Debe incluir al menos un agente") from exc
        raise HTTPException(status_code=400, detail=f"Error al crear enjambre: {detail}") from exc
