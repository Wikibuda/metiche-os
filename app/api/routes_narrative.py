from typing import List

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.db import get_session
from app.domain.narrative.models import NarrativeEntryCreate, NarrativeEntryRead
from app.domain.narrative.service import create_narrative_entry, list_narrative_entries

router = APIRouter(prefix="/narrative", tags=["narrative"])


@router.post("", response_model=NarrativeEntryRead)
def create_narrative_route(payload: NarrativeEntryCreate, session: Session = Depends(get_session)) -> NarrativeEntryRead:
    return create_narrative_entry(session, payload)


@router.get("", response_model=List[NarrativeEntryRead])
def list_narrative_route(session: Session = Depends(get_session)) -> list[NarrativeEntryRead]:
    return list_narrative_entries(session)
