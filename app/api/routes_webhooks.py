from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel import Session

from app.core.db import get_session
from app.core.config import settings
from app.domain.tasks.models import Task
from app.integrations.whatsapp_adapter import IncomingWhatsAppMessage, WhatsAppAdapter
from app.services.channel_memory_service import ChannelMemoryService
from app.services.whatsapp_event_recorder import record_whatsapp_outbound_event

router = APIRouter(prefix="/webhooks/openclaw", tags=["webhooks"])


class OpenClawWebhookPayload(BaseModel):
    payload: dict[str, Any] | None = None
    event: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    channel: str | None = None
    phone_number: str | None = None
    from_number: str | None = None
    from_: str | None = Field(default=None, alias="from")
    text: str | None = None
    content: str | None = None
    body: str | None = None
    message: dict[str, Any] | str | None = None


def _normalize_phone(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    prefix = "+" if value.startswith("+") else ""
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) < 8:
        return None
    return f"{prefix}{digits}" if prefix else digits


def _collect_strings(node: Any, *, keys: set[str], out: dict[str, list[str]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in keys and isinstance(value, str):
                candidate = value.strip()
                if candidate:
                    out.setdefault(normalized_key, []).append(candidate)
            _collect_strings(value, keys=keys, out=out)
        return
    if isinstance(node, list):
        for item in node:
            _collect_strings(item, keys=keys, out=out)


def _extract_inbound_fields(raw_payload: dict[str, Any]) -> tuple[str | None, str | None]:
    key_buckets: dict[str, list[str]] = {}
    _collect_strings(
        raw_payload,
        keys={"phone", "phone_number", "from", "from_number", "sender", "client_key", "text", "content", "body", "message"},
        out=key_buckets,
    )

    phone_candidates: list[str] = []
    for key in ("phone_number", "from_number", "from", "sender", "client_key", "phone"):
        phone_candidates.extend(key_buckets.get(key, []))
    phone_number = next((_normalize_phone(item) for item in phone_candidates if _normalize_phone(item)), None)

    text_candidates: list[str] = []
    for key in ("text", "content", "body", "message"):
        text_candidates.extend(key_buckets.get(key, []))
    message_text = next((item.strip() for item in text_candidates if item.strip()), None)
    return phone_number, message_text


def _extract_outbound_fields(raw_payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    key_buckets: dict[str, list[str]] = {}
    _collect_strings(
        raw_payload,
        keys={
            "phone",
            "phone_number",
            "to",
            "to_number",
            "target",
            "recipient",
            "client_key",
            "text",
            "content",
            "body",
            "message",
            "account",
            "bot",
            "bot_name",
            "sender_name",
            "sender",
        },
        out=key_buckets,
    )

    phone_candidates: list[str] = []
    for key in ("client_key", "to", "to_number", "target", "recipient", "phone_number", "phone"):
        phone_candidates.extend(key_buckets.get(key, []))
    client_key = next((_normalize_phone(item) for item in phone_candidates if _normalize_phone(item)), None)

    text_candidates: list[str] = []
    for key in ("text", "content", "body", "message"):
        text_candidates.extend(key_buckets.get(key, []))
    message_text = next((item.strip() for item in text_candidates if item.strip()), None)

    sender_candidates: list[str] = []
    for key in ("account", "bot_name", "bot", "sender_name", "sender"):
        sender_candidates.extend(key_buckets.get(key, []))
    sender = next((item.strip() for item in sender_candidates if item.strip()), None)
    return client_key, message_text, sender


def _emit_event(session: Session, *, task_id: str, event_type: str, summary: str, payload: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    session.connection().execute(
        text(
            """
            INSERT INTO task_events (
                id, task_id, execution_id, event_type, event_summary, importance_level,
                wonder_level, payload_json, occurred_at, created_at
            ) VALUES (
                :id, :task_id, :execution_id, :event_type, :event_summary, :importance_level,
                :wonder_level, :payload_json, :occurred_at, :created_at
            )
            """
        ),
        {
            "id": str(uuid4()),
            "task_id": task_id,
            "execution_id": None,
            "event_type": event_type,
            "event_summary": summary,
            "importance_level": "medium",
            "wonder_level": 3,
            "payload_json": json.dumps(payload, ensure_ascii=False),
            "occurred_at": now,
            "created_at": now,
        },
    )
    session.commit()


def _append_conversation_message(
    session: Session,
    *,
    client_key: str,
    direction: str,
    event_type: str,
    text: str,
    source: str,
    trace_task_id: str | None,
) -> dict[str, Any]:
    memory_service = ChannelMemoryService(session)
    previous_context = memory_service.get_context(client_key=client_key, channel="whatsapp") or {}
    conversation = list(previous_context.get("conversation_history") or [])
    now_iso = datetime.now(UTC).isoformat()
    conversation.append(
        {
            "ts": now_iso,
            "direction": direction,
            "event_type": event_type,
            "text": text,
            "source": source,
            "trace_task_id": trace_task_id,
        }
    )
    updated_context = dict(previous_context)
    updated_context["conversation_history"] = conversation[-120:]
    updated_context["last_message_direction"] = direction
    updated_context["last_message_text"] = text
    updated_context["last_message_source"] = source
    updated_context["updated_at"] = now_iso
    memory_service.save_context(client_key=client_key, channel="whatsapp", context=updated_context)
    return updated_context


@router.post("/whatsapp")
def openclaw_whatsapp_webhook(payload: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    envelope = OpenClawWebhookPayload.model_validate(payload)

    event_channel = (envelope.channel or "").strip().lower()
    if event_channel and event_channel != "whatsapp":
        raise HTTPException(status_code=400, detail="channel_not_supported")

    merged_payload: dict[str, Any] = {}
    for chunk in (payload, envelope.model_dump(exclude_none=True, by_alias=True), envelope.payload or {}, envelope.event or {}, envelope.data or {}):
        if isinstance(chunk, dict):
            merged_payload.update(chunk)

    phone_number, message_text = _extract_inbound_fields(merged_payload)
    if not phone_number or not message_text:
        raise HTTPException(status_code=400, detail="missing_phone_or_text")

    adapter = WhatsAppAdapter(session)
    try:
        result = adapter.handle_incoming_message(
            IncomingWhatsAppMessage(phone_number=phone_number, text=message_text)
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _emit_event(
        session,
        task_id=result.trace_task_id,
        event_type="whatsapp_message_received",
        summary="Webhook OpenClaw recibio mensaje entrante de WhatsApp",
        payload={
            "client_key": result.client_key,
            "text": message_text,
            "source": "openclaw_webhook",
            "raw_payload": merged_payload,
        },
    )
    _append_conversation_message(
        session,
        client_key=result.client_key,
        direction="inbound",
        event_type="whatsapp_message_received",
        text=message_text,
        source="openclaw_webhook_inbound",
        trace_task_id=result.trace_task_id,
    )

    task = session.get(Task, result.trace_task_id)
    if task is not None and task.status == "running":
        task.status = "done"
        task.updated_at = datetime.now(UTC)
        session.add(task)
        session.commit()

    return {
        "ok": True,
        "channel": "whatsapp",
        "client_key": result.client_key,
        "trace_task_id": result.trace_task_id,
        "event_type": "whatsapp_message_received",
        "message_preview": message_text[:120],
    }


@router.post("/whatsapp/outbound")
def openclaw_whatsapp_outbound_webhook(payload: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    envelope = OpenClawWebhookPayload.model_validate(payload)

    event_channel = (envelope.channel or "").strip().lower()
    if event_channel and event_channel != "whatsapp":
        raise HTTPException(status_code=400, detail="channel_not_supported")

    merged_payload: dict[str, Any] = {}
    for chunk in (payload, envelope.model_dump(exclude_none=True, by_alias=True), envelope.payload or {}, envelope.event or {}, envelope.data or {}):
        if isinstance(chunk, dict):
            merged_payload.update(chunk)

    try:
        return record_whatsapp_outbound_event(
            session,
            raw_payload=merged_payload,
            source_label="openclaw_webhook_outbound",
            default_sender_name=settings.openclaw_autoreply_sender_name,
        )
    except ValueError as exc:
        if str(exc) == "missing_client_key_or_text":
            raise HTTPException(status_code=400, detail="missing_client_key_or_text") from exc
        raise
