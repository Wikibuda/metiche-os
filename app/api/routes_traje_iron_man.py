from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.traje_iron_man.operaciones import get_traje_status, run_traje_operation

router = APIRouter(prefix="/api/traje-iron-man", tags=["traje-iron-man"])


class TrajeRunRequest(BaseModel):
    operacion: Literal["archivar", "limpiar-low", "etiquetar"]
    lote: int = Field(default=20, ge=1, le=200)
    dry_run: bool = False


@router.post("/run")
def run_traje_iron_man(payload: TrajeRunRequest) -> dict:
    try:
        return run_traje_operation(
            operacion=payload.operacion,
            lote=payload.lote,
            dry_run=payload.dry_run,
            trigger="api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"traje_iron_man_error:{exc}") from exc


@router.get("/status")
def get_traje_iron_man_status() -> dict:
    return get_traje_status()
