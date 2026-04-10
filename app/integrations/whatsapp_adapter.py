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
class IncomingWhatsAppMessage:
    phone_number: str
    text: str


@dataclass
class OutboundWhatsAppMessage:
    client_key: str
    text: str


@dataclass
class WhatsAppAdapterResult:
    client_key: str
    loaded_context: dict[str, Any]
    updated_context: dict[str, Any]
    prompt: str
    trace_task_id: str


class WhatsAppAdapter:
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

    def handle_incoming_message(self, message: IncomingWhatsAppMessage) -> WhatsAppAdapterResult:
        client_key = self._extract_client_key(message.phone_number)
        trace_task = self._create_trace_task(client_key=client_key, message_text=message.text)

        loaded_context = self._get_context_from_api(client_key=client_key)
        self._emit_task_event(
            task_id=trace_task.id,
            event_type="whatsapp_memory_read",
            summary="WhatsApp adapter recupero contexto desde memoria compartida",
            payload={"client_key": client_key, "channel": "whatsapp", "context": loaded_context},
        )
        prompt = self._build_prompt(context=loaded_context, user_message=message.text)
        updated_context = dict(loaded_context)
        updated_context["last_user_message"] = message.text
        updated_context["last_channel"] = "whatsapp"
        updated_context["updated_at"] = datetime.now(UTC).isoformat()
        self._save_context_to_api(client_key=client_key, context=updated_context)
        self._emit_task_event(
            task_id=trace_task.id,
            event_type="whatsapp_memory_write",
            summary="WhatsApp adapter guardo contexto en memoria compartida",
            payload={"client_key": client_key, "channel": "whatsapp", "context": updated_context},
        )
        return WhatsAppAdapterResult(
            client_key=client_key,
            loaded_context=loaded_context,
            updated_context=updated_context,
            prompt=prompt,
            trace_task_id=trace_task.id,
        )

    def send_message(self, message: OutboundWhatsAppMessage) -> dict[str, Any]:
        client_key = self._extract_client_key(message.client_key)
        trace_task = self._create_trace_task(client_key=client_key, message_text=message.text, direction="outbound")

        loaded_context = self._get_context_from_api(client_key=client_key)
        self._emit_task_event(
            task_id=trace_task.id,
            event_type="whatsapp_memory_read",
            summary="WhatsApp adapter recupero contexto antes de send_message",
            payload={"client_key": client_key, "channel": "whatsapp", "context": loaded_context, "action": "send_message"},
        )

        updated_context = dict(loaded_context)
        updated_context["last_outbound_message"] = message.text
        updated_context["last_channel"] = "whatsapp"
        updated_context["updated_at"] = datetime.now(UTC).isoformat()
        self._save_context_to_api(client_key=client_key, context=updated_context)
        self._emit_task_event(
            task_id=trace_task.id,
            event_type="whatsapp_memory_write",
            summary="WhatsApp adapter guardo contexto tras send_message",
            payload={"client_key": client_key, "channel": "whatsapp", "context": updated_context, "action": "send_message"},
        )
        delivery_payload = {"delivery": "simulated", "status": "sent"}
        self._emit_task_event(
            task_id=trace_task.id,
            event_type="whatsapp_send_message",
            summary="WhatsApp adapter envio mensaje simulado",
            payload={"client_key": client_key, "text": message.text, "result": delivery_payload},
        )
        return {
            "success": True,
            "channel": "whatsapp",
            "client_key": client_key,
            "message": message.text,
            "trace_task_id": trace_task.id,
            "payload": delivery_payload,
            "context": updated_context,
        }

    def _extract_client_key(self, phone_number: str) -> str:
        cleaned = (phone_number or "").strip()
        if not cleaned:
            raise ValueError("phone_number_required")
        return cleaned

    def _build_prompt(self, *, context: dict[str, Any], user_message: str) -> str:
        context_block = json.dumps(context, ensure_ascii=False, sort_keys=True) if context else "{}"
        return (
            "Canal: whatsapp\n"
            f"Contexto previo: {context_block}\n"
            f"Mensaje del usuario: {user_message}\n"
            "Responde manteniendo continuidad con el contexto."
        )

    def _get_context_from_api(self, *, client_key: str) -> dict[str, Any]:
        path = f"/channel-memory/{client_key}?channel=whatsapp"
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
        return ChannelMemoryService(self.session).get_context(client_key=client_key, channel="whatsapp") or {}

    def _save_context_to_api(self, *, client_key: str, context: dict[str, Any]) -> None:
        path = f"/channel-memory/{client_key}"
        body = {"context": context}
        headers = {"X-Channel-Name": "whatsapp"}
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
        ChannelMemoryService(self.session).save_context(client_key=client_key, channel="whatsapp", context=context)

    def _create_trace_task(self, *, client_key: str, message_text: str, direction: str = "inbound") -> Task:
        now = datetime.now(UTC)
        task = Task(
            title=f"WhatsApp {direction} {client_key}",
            description=f"Adapter trace message ({direction}): {message_text}",
            execution_mode="immediate",
            task_type="whatsapp",
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
