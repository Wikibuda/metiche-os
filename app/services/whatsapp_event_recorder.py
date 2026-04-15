from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import Session

from app.services.channel_memory_service import ChannelMemoryService


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


def extract_outbound_fields(raw_payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
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
    text_value: str,
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
            "text": text_value,
            "source": source,
            "trace_task_id": trace_task_id,
        }
    )
    updated_context = dict(previous_context)
    updated_context["conversation_history"] = conversation[-120:]
    updated_context["last_message_direction"] = direction
    updated_context["last_message_text"] = text_value
    updated_context["last_message_source"] = source
    updated_context["updated_at"] = now_iso
    memory_service.save_context(client_key=client_key, channel="whatsapp", context=updated_context)
    return updated_context


def outbound_event_exists_by_correlation_id(session: Session, correlation_id: str) -> bool:
    candidate = (correlation_id or "").strip()
    if not candidate:
        return False
    needle = f'%"{candidate}"%'
    row = session.connection().execute(
        text(
            """
            SELECT 1
            FROM task_events
            WHERE event_type = 'whatsapp_message_sent'
              AND payload_json LIKE :needle
            LIMIT 1
            """
        ),
        {"needle": needle},
    ).first()
    return row is not None


def record_whatsapp_outbound_event(
    session: Session,
    *,
    raw_payload: dict[str, Any],
    source_label: str,
    default_sender_name: str,
    summary: str = "Webhook OpenClaw recibio mensaje saliente de WhatsApp",
) -> dict[str, Any]:
    client_key, message_text, sender = extract_outbound_fields(raw_payload)
    if not client_key or not message_text:
        raise ValueError("missing_client_key_or_text")

    source_bot = (sender or default_sender_name).strip()
    trace_task_id = str(uuid4())
    _emit_event(
        session,
        task_id=trace_task_id,
        event_type="whatsapp_message_sent",
        summary=summary,
        payload={
            "client_key": client_key,
            "text": message_text,
            "source": source_label,
            "bot_name": source_bot,
            "raw_payload": raw_payload,
        },
    )
    updated_context = _append_conversation_message(
        session,
        client_key=client_key,
        direction="outbound",
        event_type="whatsapp_message_sent",
        text_value=message_text,
        source=source_bot,
        trace_task_id=trace_task_id,
    )
    return {
        "ok": True,
        "channel": "whatsapp",
        "client_key": client_key,
        "event_type": "whatsapp_message_sent",
        "source_bot": source_bot,
        "message_preview": message_text[:120],
        "memory_entries": len(updated_context.get("conversation_history") or []),
    }
