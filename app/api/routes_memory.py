from datetime import datetime, UTC
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryEntry(BaseModel):
    title: str
    content: str
    event_type: str = "learning"  # decision, error, success, learning
    importance_level: str = "medium"  # low, medium, high
    wonder_level: int = 3  # 1-5
    source: str = "api"
    related_task_id: Optional[str] = None


class MemoryEntryResponse(MemoryEntry):
    id: str
    created_at: datetime


# Almacenamiento en memoria (compatibilidad mínima para Fase 5)
_memory_store: list[dict] = []


@router.post("/", response_model=MemoryEntryResponse)
async def create_memory_entry(entry: MemoryEntry):
    """Registra una nueva entrada en el pool de memoria."""
    new_entry = entry.model_dump()
    new_entry["id"] = str(uuid4())
    new_entry["created_at"] = datetime.now(UTC)
    _memory_store.append(new_entry)
    return new_entry


@router.get("/", response_model=list[MemoryEntryResponse])
async def get_memory_entries(
    event_type: Optional[str] = None,
    importance_level: Optional[str] = None,
    wonder_level: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Consulta entradas de memoria con filtros."""
    results = _memory_store
    if event_type:
        results = [e for e in results if e["event_type"] == event_type]
    if importance_level:
        results = [e for e in results if e["importance_level"] == importance_level]
    if wonder_level:
        results = [e for e in results if e["wonder_level"] == wonder_level]
    return results[offset : offset + limit]


@router.get("/stats")
async def get_memory_stats():
    """Estadísticas básicas del pool de memoria."""
    total = len(_memory_store)
    by_type: dict[str, int] = {}
    for entry in _memory_store:
        entry_type = entry["event_type"]
        by_type[entry_type] = by_type.get(entry_type, 0) + 1
    return {"total_entries": total, "by_event_type": by_type}


@router.get("/{entry_id}", response_model=MemoryEntryResponse)
async def get_memory_entry(entry_id: str):
    """Obtiene una entrada específica por ID."""
    for entry in _memory_store:
        if entry["id"] == entry_id:
            return entry
    raise HTTPException(status_code=404, detail="Memory entry not found")
