from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel


class Actor(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    code: str = Field(index=True, unique=True)
    label: str
    identity_type: str
    display_name: str
    emoji: Optional[str] = None
    persona_summary: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SoulProfile(SQLModel, table=True):
    actor_id: str = Field(foreign_key="actor.id", primary_key=True)
    soul_name: str
    soul_essence: str
    symbolic_world: Optional[str] = None
    canonical_emojis: Optional[str] = None
    humor_style: Optional[str] = None
    relationship_center: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CanonicalPhrase(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    actor_id: str = Field(foreign_key="actor.id")
    code: str = Field(index=True, unique=True)
    phrase_text: str
    phrase_context: Optional[str] = None
    tone: Optional[str] = None
    emoji_signature: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
