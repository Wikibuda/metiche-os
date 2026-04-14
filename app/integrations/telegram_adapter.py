from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.domain.tasks.models import Task
from app.services.channel_memory_service import ChannelMemoryService


@dataclass
class IncomingTelegramMessage:
    chat_id: str
    text: str


@dataclass
class OutboundTelegramMessage:
    client_key: str
    text: str


@dataclass
class TelegramAdapterResult:
    client_key: str
    loaded_context: dict[str, Any]
    updated_context: dict[str, Any]
    prompt: str
    trace_task_id: str


class TelegramAdapter:
    def __init__(
        self,
        session: Session,
        *,
        api_client: Any | None = None,
        memory_api_base_url: str | None = None,
    ) -> None:
        self.session = session
        self.api_client = api_client
        self.memory_api_base_url = memory_api_base_url or getattr(settings, "memory_api_base_url", "internal://memory")
        self.allowed_ids = self._parse_allowed_ids(settings.telegram_allowed_ids)
        self.sandbox_mode = bool(settings.telegram_sandbox_mode)

    def handle_incoming_message(self, message: IncomingTelegramMessage) -> TelegramAdapterResult:
        client_key = self._extract_client_key(message.chat_id)
        trace_task = self._create_trace_task(client_key=client_key, message_text=message.text)
        self._validate_safelist(client_key=client_key, trace_task_id=trace_task.id, direction="inbound")
        try:
            loaded_context = self._get_context_from_api(client_key=client_key)
            self._emit_task_event(
                task_id=trace_task.id,
                event_type="telegram_memory_read",
                summary="Telegram adapter recupero contexto desde memoria compartida",
                payload={"client_key": client_key, "channel": "telegram", "context": loaded_context},
            )
            prompt = self._build_prompt(context=loaded_context, user_message=message.text)
            updated_context = dict(loaded_context)
            updated_context["last_user_message"] = message.text
            updated_context["last_channel"] = "telegram"
            updated_context["updated_at"] = datetime.now(UTC).isoformat()
            self._save_context_to_api(client_key=client_key, context=updated_context)
            self._emit_task_event(
                task_id=trace_task.id,
                event_type="telegram_memory_write",
                summary="Telegram adapter guardo contexto en memoria compartida",
                payload={"client_key": client_key, "channel": "telegram", "context": updated_context},
            )
            self._set_task_status(task=trace_task, status="done")
            return TelegramAdapterResult(
                client_key=client_key,
                loaded_context=loaded_context,
                updated_context=updated_context,
                prompt=prompt,
                trace_task_id=trace_task.id,
            )
        except Exception:
            self._set_task_status(task=trace_task, status="failed")
            raise

    def send_message(self, message: OutboundTelegramMessage) -> dict[str, Any]:
        client_key = self._extract_client_key(message.client_key)
        trace_task = self._create_trace_task(client_key=client_key, message_text=message.text, direction="outbound")
        self._validate_safelist(client_key=client_key, trace_task_id=trace_task.id, direction="outbound")

        loaded_context = self._get_context_from_api(client_key=client_key)
        self._emit_task_event(
            task_id=trace_task.id,
            event_type="telegram_memory_read",
            summary="Telegram adapter recupero contexto antes de send_message",
            payload={"client_key": client_key, "channel": "telegram", "context": loaded_context, "action": "send_message"},
        )

        updated_context = dict(loaded_context)
        updated_context["last_outbound_message"] = message.text
        updated_context["last_channel"] = "telegram"
        updated_context["updated_at"] = datetime.now(UTC).isoformat()
        self._save_context_to_api(client_key=client_key, context=updated_context)
        self._emit_task_event(
            task_id=trace_task.id,
            event_type="telegram_memory_write",
            summary="Telegram adapter guardo contexto tras send_message",
            payload={"client_key": client_key, "channel": "telegram", "context": updated_context, "action": "send_message"},
        )
        try:
            delivery_payload = self._send_via_telegram_api(client_key=client_key, text=message.text, trace_task_id=trace_task.id)
            self._emit_task_event(
                task_id=trace_task.id,
                event_type="telegram_send_message",
                summary="Telegram adapter envio mensaje",
                payload={"client_key": client_key, "text": message.text, "success": True, "result": delivery_payload},
            )
            self._set_task_status(task=trace_task, status="done")
            return {
                "success": True,
                "channel": "telegram",
                "client_key": client_key,
                "message": message.text,
                "trace_task_id": trace_task.id,
                "payload": delivery_payload,
                "context": updated_context,
            }
        except Exception as exc:
            self._emit_task_event(
                task_id=trace_task.id,
                event_type="telegram_send_message",
                summary="Telegram adapter fallo al enviar mensaje",
                payload={"client_key": client_key, "text": message.text, "success": False, "error": str(exc)},
            )
            self._set_task_status(task=trace_task, status="failed")
            raise

    def _send_via_telegram_api(self, *, client_key: str, text: str, trace_task_id: str) -> dict[str, Any]:
        if self.sandbox_mode:
            payload = {"delivery": "simulated", "status": "sent", "sandbox": True}
            self._emit_task_event(
                task_id=trace_task_id,
                event_type="telegram_sandbox_mode",
                summary="Telegram sandbox activo: envio simulado",
                payload={"client_key": client_key, "text": text, "sandbox": True},
            )
            return payload
        if self.api_client is not None:
            response = self.api_client.post(
                "/telegram/send",
                json={"chat_id": client_key, "text": text},
            )
            if response.status_code != 200:
                raise RuntimeError(f"telegram_send_failed:{response.status_code}:{response.text}")
            payload = response.json()
            return payload if isinstance(payload, dict) else {"delivery": "real", "status": "sent"}
        if not settings.telegram_bot_token:
            raise RuntimeError("telegram_bot_token_required_when_sandbox_disabled")
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, json={"chat_id": client_key, "text": text})
        if response.status_code != 200:
            raise RuntimeError(f"telegram_send_failed:{response.status_code}:{response.text}")
        payload = response.json()
        if not isinstance(payload, dict):
            return {"delivery": "real", "status": "sent"}
        if not bool(payload.get("ok")):
            raise RuntimeError(f"telegram_send_failed:{payload}")
        return payload

    def _extract_client_key(self, chat_id: str) -> str:
        cleaned = (chat_id or "").strip()
        if not cleaned:
            raise ValueError("chat_id_required")
        if not cleaned.lstrip("-").isdigit():
            raise ValueError(f"invalid_telegram_chat_id:{cleaned}")
        return cleaned

    def _parse_allowed_ids(self, raw_value: str) -> set[str]:
        ids = set()
        for token in (raw_value or "").split(","):
            normalized = token.strip()
            if normalized:
                ids.add(normalized)
        return ids

    def _validate_safelist(self, *, client_key: str, trace_task_id: str, direction: str) -> None:
        if client_key in self.allowed_ids:
            return
        self._emit_task_event(
            task_id=trace_task_id,
            event_type="telegram_security_block",
            summary="Telegram security block por chat_id fuera de safelist",
            payload={"client_key": client_key, "direction": direction, "allowed_ids": sorted(self.allowed_ids)},
        )
        raise PermissionError(f"chat_id_not_allowed:{client_key}")

    def _build_prompt(self, *, context: dict[str, Any], user_message: str) -> str:
        context_block = json.dumps(context, ensure_ascii=False, sort_keys=True) if context else "{}"
        return (
            "Canal: telegram\n"
            f"Contexto previo: {context_block}\n"
            f"Mensaje del usuario: {user_message}\n"
            "Responde manteniendo continuidad con el contexto."
        )

    def _get_context_from_api(self, *, client_key: str) -> dict[str, Any]:
        path = f"/channel-memory/{client_key}?channel=telegram"
        if self.api_client is not None:
            response = self.api_client.get(path)
            if response.status_code == 404:
                return {}
            if response.status_code != 200:
                raise RuntimeError(f"memory_get_failed:{response.status_code}:{response.text}")
            payload = response.json()
            context = payload.get("context")
            return context if isinstance(context, dict) else {}
        if self.memory_api_base_url.startswith("http"):
            with httpx.Client(base_url=self.memory_api_base_url, timeout=10) as client:
                response = client.get(path)
            if response.status_code == 404:
                return {}
            if response.status_code != 200:
                raise RuntimeError(f"memory_get_failed:{response.status_code}:{response.text}")
            payload = response.json()
            context = payload.get("context")
            return context if isinstance(context, dict) else {}
        return ChannelMemoryService(self.session).get_context(client_key=client_key, channel="telegram") or {}

    def _save_context_to_api(self, *, client_key: str, context: dict[str, Any]) -> None:
        path = f"/channel-memory/{client_key}"
        body = {"context": context}
        headers = {"X-Channel-Name": "telegram"}
        if self.api_client is not None:
            response = self.api_client.post(path, json=body, headers=headers)
            if response.status_code != 200:
                raise RuntimeError(f"memory_post_failed:{response.status_code}:{response.text}")
            return
        if self.memory_api_base_url.startswith("http"):
            with httpx.Client(base_url=self.memory_api_base_url, timeout=10) as client:
                response = client.post(path, json=body, headers=headers)
            if response.status_code != 200:
                raise RuntimeError(f"memory_post_failed:{response.status_code}:{response.text}")
            return
        ChannelMemoryService(self.session).save_context(client_key=client_key, channel="telegram", context=context)

    def _create_trace_task(self, *, client_key: str, message_text: str, direction: str = "inbound") -> Task:
        now = datetime.now(UTC)
        task = Task(
            title=f"Telegram {direction} {client_key}",
            description=f"Adapter trace message ({direction}): {message_text}",
            execution_mode="immediate",
            task_type="telegram",
            status="running",
            created_at=now,
            updated_at=now,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def _emit_task_event(self, *, task_id: str, event_type: str, summary: str, payload: dict[str, Any]) -> None:
        conn = self.session.connection()
        now = datetime.now(UTC)
        try:
            conn.execute(
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
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _set_task_status(self, *, task: Task, status: str) -> None:
        task.status = status
        task.updated_at = datetime.now(UTC)
        self.session.add(task)
        self.session.commit()
