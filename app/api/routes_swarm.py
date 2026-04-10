from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.core.db import get_session
from app.domain.swarm.models import SwarmCreate, SwarmHistoryRead, SwarmRead, SwarmRunCreate, SwarmRunRead, SwarmSummaryRead
from app.domain.swarm.service import create_swarm, get_swarm, get_swarm_history, list_swarms, run_swarm_cycle

router = APIRouter(prefix="/swarm", tags=["swarm"])


@router.post("", response_model=SwarmRead)
def create_swarm_route(payload: SwarmCreate, session: Session = Depends(get_session)) -> SwarmRead:
    try:
        return create_swarm(session, payload)
    except ValueError as exc:
        detail = str(exc)
        if detail == "invalid_policy":
            raise HTTPException(status_code=400, detail="Policy no valida") from exc
        if detail == "empty_agents":
            raise HTTPException(status_code=400, detail="Debe incluir al menos un agente") from exc
        if detail.startswith("invalid_agents:"):
            invalid = detail.split(":", 1)[1]
            raise HTTPException(status_code=400, detail=f"Agentes invalidos: {invalid}") from exc
        raise HTTPException(status_code=400, detail="Payload invalido para crear swarm") from exc


@router.get("", response_model=list[SwarmSummaryRead])
def list_swarms_route(
    limit: int = Query(default=20, ge=1, le=50),
    session: Session = Depends(get_session),
) -> list[SwarmSummaryRead]:
    return list_swarms(session, limit)


@router.get("/{swarm_id}", response_model=SwarmRead)
def get_swarm_route(swarm_id: str, session: Session = Depends(get_session)) -> SwarmRead:
    row = get_swarm(session, swarm_id)
    if not row:
        raise HTTPException(status_code=404, detail="Swarm no encontrado")
    return row


@router.post("/{swarm_id}/run", response_model=SwarmRunRead)
def run_swarm_route(swarm_id: str, payload: SwarmRunCreate, session: Session = Depends(get_session)) -> SwarmRunRead:
    try:
        result = run_swarm_cycle(session, swarm_id, payload)
    except ValueError as exc:
        if str(exc) == "swarm_without_agents":
            raise HTTPException(status_code=409, detail="El swarm no tiene agentes asignados") from exc
        raise HTTPException(status_code=400, detail="No se pudo ejecutar el swarm") from exc
    if not result:
        raise HTTPException(status_code=404, detail="Swarm no encontrado")
    return result


@router.get("/{swarm_id}/history", response_model=SwarmHistoryRead)
def get_swarm_history_route(swarm_id: str, session: Session = Depends(get_session)) -> SwarmHistoryRead:
    row = get_swarm_history(session, swarm_id)
    if not row:
        raise HTTPException(status_code=404, detail="Swarm no encontrado")
    return row
