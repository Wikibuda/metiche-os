from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


class NarrativeEntry(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str
    body: str
    narrative_type: str = Field(default="chronicle")
    wonder_level: int = Field(default=3)
    narrator_code: str = Field(default="metiche")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NarrativeEntryCreate(BaseModel):
    title: str
    body: str
    narrative_type: str = "chronicle"
    wonder_level: int = 3
    narrator_code: str = "metiche"


class NarrativeEntryRead(BaseModel):
    id: str
    title: str
    body: str
    narrative_type: str
    wonder_level: int
    narrator_code: str
    created_at: datetime

    @classmethod
    def from_model(cls, item: NarrativeEntry) -> "NarrativeEntryRead":
        return cls.model_validate(item.model_dump())
