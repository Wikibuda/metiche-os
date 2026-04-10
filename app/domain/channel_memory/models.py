from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


class ChannelMemory(SQLModel, table=True):
    __tablename__ = "channel_memory"
    __table_args__ = (UniqueConstraint("client_key", "channel", name="uq_channel_memory_client_channel"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    client_key: str = Field(index=True)
    channel: str = Field(index=True)
    context: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
