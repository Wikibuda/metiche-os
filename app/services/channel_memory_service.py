from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from app.domain.channel_memory.models import ChannelMemory


class ChannelMemoryService:
    def __init__(self, session: Session):
        self.session = session

    def save_context(self, client_key: str, channel: str, context: dict[str, Any]) -> ChannelMemory:
        clean_client_key = (client_key or "").strip()
        clean_channel = (channel or "").strip().lower()
        if not clean_client_key:
            raise ValueError("client_key_required")
        if not clean_channel:
            raise ValueError("channel_required")
        if not isinstance(context, dict):
            raise ValueError("context_must_be_json_object")

        existing = self.session.exec(
            select(ChannelMemory).where(
                ChannelMemory.client_key == clean_client_key,
                ChannelMemory.channel == clean_channel,
            )
        ).first()
        now = datetime.now(UTC)
        if existing:
            existing.context = context
            existing.updated_at = now
            self.session.add(existing)
            self.session.commit()
            self.session.refresh(existing)
            return existing

        row = ChannelMemory(
            client_key=clean_client_key,
            channel=clean_channel,
            context=context,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def get_context(self, client_key: str, channel: str) -> dict[str, Any] | None:
        clean_client_key = (client_key or "").strip()
        clean_channel = (channel or "").strip().lower()
        if not clean_client_key or not clean_channel:
            return None
        row = self.session.exec(
            select(ChannelMemory)
            .where(
                ChannelMemory.client_key == clean_client_key,
                ChannelMemory.channel == clean_channel,
            )
            .order_by(ChannelMemory.updated_at.desc())
        ).first()
        return row.context if row else None

    def delete_context(self, client_key: str, channel: str) -> bool:
        clean_client_key = (client_key or "").strip()
        clean_channel = (channel or "").strip().lower()
        if not clean_client_key:
            raise ValueError("client_key_required")
        if not clean_channel:
            raise ValueError("channel_required")
        row = self.session.exec(
            select(ChannelMemory).where(
                ChannelMemory.client_key == clean_client_key,
                ChannelMemory.channel == clean_channel,
            )
        ).first()
        if not row:
            return False
        self.session.delete(row)
        self.session.commit()
        return True
