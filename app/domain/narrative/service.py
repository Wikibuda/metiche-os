from datetime import date, datetime, time
from pathlib import Path

from sqlmodel import Session, select

from app.core.config import settings
from app.domain.narrative.models import NarrativeEntry, NarrativeEntryCreate, NarrativeEntryRead
from app.projections.bitacora import build_bitacora


def create_narrative_entry(session: Session, payload: NarrativeEntryCreate) -> NarrativeEntryRead:
    item = NarrativeEntry(
        title=payload.title,
        body=payload.body,
        narrative_type=payload.narrative_type,
        wonder_level=payload.wonder_level,
        narrator_code=payload.narrator_code,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    build_bitacora(session, Path(settings.projections_root) / "bitacora" / "bitacora_de_asombros.md")
    return NarrativeEntryRead.from_model(item)


def list_narrative_entries(session: Session) -> list[NarrativeEntryRead]:
    rows = session.exec(select(NarrativeEntry).order_by(NarrativeEntry.created_at.desc())).all()
    return [NarrativeEntryRead.from_model(row) for row in rows]


def list_recent_narratives(session: Session, limit: int = 7) -> list[NarrativeEntryRead]:
    safe_limit = max(1, min(limit, 100))
    rows = session.exec(select(NarrativeEntry).order_by(NarrativeEntry.created_at.desc()).limit(safe_limit)).all()
    return [NarrativeEntryRead.from_model(row) for row in rows]


def list_narratives_for_day(session: Session, target_day: date) -> list[NarrativeEntryRead]:
    start = datetime.combine(target_day, time.min)
    end = datetime.combine(target_day, time.max)
    rows = session.exec(
        select(NarrativeEntry)
        .where(NarrativeEntry.created_at >= start, NarrativeEntry.created_at <= end)
        .order_by(NarrativeEntry.created_at.desc())
    ).all()
    return [NarrativeEntryRead.from_model(row) for row in rows]


def search_narratives(session: Session, query: str, limit: int = 10) -> list[NarrativeEntryRead]:
    safe_limit = max(1, min(limit, 100))
    q = query.strip()
    if not q:
        return []
    like = f"%{q}%"
    rows = session.exec(
        select(NarrativeEntry)
        .where((NarrativeEntry.title.like(like)) | (NarrativeEntry.body.like(like)))
        .order_by(NarrativeEntry.created_at.desc())
        .limit(safe_limit)
    ).all()
    return [NarrativeEntryRead.from_model(row) for row in rows]
