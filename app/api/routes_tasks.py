from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.db import get_session
from app.domain.tasks.models import EngineDispatchRead, EscalationRead, OperationalOverviewRead, QueueEntryRead, RouteResolutionRead, TaskCreate, TaskEnqueueCreate, TaskFlowRead, TaskQueueProcessRead, TaskRead, TaskRunCreate
from app.domain.tasks.service import build_operational_overview, create_task, enqueue_task, get_engine_dispatch, get_task_escalation, get_task_flow, get_task_route_resolution, list_queue_entries, list_tasks, process_next_task, run_task_flow

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead)
def create_task_route(payload: TaskCreate, session: Session = Depends(get_session)) -> TaskRead:
    return create_task(session, payload)


@router.get("", response_model=List[TaskRead])
def list_tasks_route(session: Session = Depends(get_session)) -> list[TaskRead]:
    return list_tasks(session)


@router.post("/run", response_model=TaskFlowRead)
def run_task_route(payload: TaskRunCreate, session: Session = Depends(get_session)) -> TaskFlowRead:
    return run_task_flow(session, payload)


@router.get("/{task_id}/flow", response_model=TaskFlowRead)
def get_task_flow_route(task_id: str, session: Session = Depends(get_session)) -> TaskFlowRead:
    flow = get_task_flow(session, task_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flujo no encontrado")
    return flow


@router.post("/enqueue", response_model=QueueEntryRead)
def enqueue_task_route(payload: TaskEnqueueCreate, session: Session = Depends(get_session)) -> QueueEntryRead:
    return enqueue_task(session, payload)


@router.get("/queue", response_model=List[QueueEntryRead])
def list_queue_route(session: Session = Depends(get_session)) -> list[QueueEntryRead]:
    return list_queue_entries(session)


@router.post("/process-next", response_model=TaskQueueProcessRead)
def process_next_task_route(session: Session = Depends(get_session)) -> TaskQueueProcessRead:
    result = process_next_task(session)
    if not result:
        raise HTTPException(status_code=404, detail="Cola vacía")
    return result


@router.get("/{task_id}/route", response_model=RouteResolutionRead)
def get_task_route_route(task_id: str, session: Session = Depends(get_session)) -> RouteResolutionRead:
    route_resolution = get_task_route_resolution(session, task_id)
    if not route_resolution:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    return route_resolution


@router.get("/{task_id}/dispatch", response_model=EngineDispatchRead)
def get_task_dispatch_route(task_id: str, session: Session = Depends(get_session)) -> EngineDispatchRead:
    dispatch = get_engine_dispatch(session, task_id)
    if not dispatch:
        raise HTTPException(status_code=404, detail="Dispatch no encontrado")
    return dispatch


@router.get("/overview", response_model=OperationalOverviewRead)
def get_tasks_overview_route(session: Session = Depends(get_session)) -> OperationalOverviewRead:
    return build_operational_overview(session)


@router.get("/{task_id}/escalation", response_model=EscalationRead)
def get_task_escalation_route(task_id: str, session: Session = Depends(get_session)) -> EscalationRead:
    escalation = get_task_escalation(session, task_id)
    if not escalation:
        raise HTTPException(status_code=404, detail="Escalamiento no encontrado")
    return escalation
