"""
Traje Iron Man — API endpoints para operaciones masivas en Plane.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.traje_iron_man.operaciones import get_traje_status, run_traje_operation

router = APIRouter(prefix="/api/traje-iron-man", tags=["traje-iron-man"])


class TrajeRunRequest(BaseModel):
    operacion: Literal["archivar", "limpiar-low", "etiquetar"] = Field(default="limpiar-low")
    lote: int = Field(default=20, ge=5, le=200)
    dry_run: bool = Field(default=True)
    trigger: str = Field(default="api")


@router.post("/run")
def run_traje_iron_man(payload: TrajeRunRequest):
    """Ejecuta operación del Traje Iron Man."""
    try:
        result = run_traje_operation(
            operacion=payload.operacion,
            lote=payload.lote,
            dry_run=payload.dry_run,
            trigger=payload.trigger,
        )
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"traje_iron_man_error: {e}")


@router.get("/status")
def get_traje_iron_man_status():
    """Estado actual del Traje Iron Man."""
    return get_traje_status()
