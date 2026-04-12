from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


class Rule(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    code: str = Field(index=True, unique=True)
    title: str
    description: str
    rule_group: str = Field(default="operational")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RuleRead(BaseModel):
    id: str
    code: str
    title: str
    description: str
    rule_group: str
    is_active: bool
    created_at: datetime

    @classmethod
    def from_model(cls, rule: Rule) -> "RuleRead":
        return cls.model_validate(rule, from_attributes=True)
