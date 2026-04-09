from typing import List

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.db import get_session
from app.domain.rules import Rule, RuleRead

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_model=List[RuleRead])
def list_rules_route(session: Session = Depends(get_session)) -> list[RuleRead]:
    rows = session.exec(select(Rule).order_by(Rule.code.asc())).all()
    return [RuleRead.from_model(row) for row in rows]
