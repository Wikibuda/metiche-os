from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
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
        self.allowed_numbers = self._parse_allowed_numbers(settings.whatsapp_allowed_numbers)
        self.sandbox_mode = bool(settings.whatsapp_sandbox_mode)

    def handle_incoming_message(self, message: IncomingWhatsAppMessage) -> WhatsAppAdapterResult:
        client_key = self._extract_client_key(message.phone_number)
        trace_task = self._create_trace_task(client_key=client_key, message_text=message.text)
        try:
            self._validate_safelist(client_key=client_key, trace_task_id=trace_task.id, direction="inbound")
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
            self._set_task_status(task=trace_task, status="done")
            return WhatsAppAdapterResult(
                client_key=client_key,
                loaded_context=loaded_context,
                updated_context=updated_context,
                prompt=prompt,
                trace_task_id=trace_task.id,
            )
        except Exception:
            self._set_task_status(task=trace_task, status="failed")
            raise

    def send_message(self, message: OutboundWhatsAppMessage) -> dict[str, Any]:
        client_key = self._extract_client_key(message.client_key)
        trace_task = self._create_trace_task(client_key=client_key, message_text=message.text, direction="outbound")
        try:
            self._validate_safelist(client_key=client_key, trace_task_id=trace_task.id, direction="outbound")

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

            delivery_payload = self._send_via_whatsapp_api(client_key=client_key, text=message.text, trace_task_id=trace_task.id)
            self._emit_task_event(
                task_id=trace_task.id,
                event_type="whatsapp_send_message",
                summary="WhatsApp adapter envio mensaje",
                payload={
                    "client_key": client_key,
                    "text": message.text,
                    "success": True,
                    "result": delivery_payload,
                },
            )
            self._set_task_status(task=trace_task, status="done")
            return {
                "success": True,
                "channel": "whatsapp",
                "client_key": client_key,
                "message": message.text,
                "trace_task_id": trace_task.id,
                "payload": delivery_payload,
                "context": updated_context,
            }
        except Exception as exc:
            self._emit_task_event(
                task_id=trace_task.id,
                event_type="whatsapp_send_message",
                summary="WhatsApp adapter fallo al enviar mensaje",
                payload={
                    "client_key": client_key,
                    "text": message.text,
                    "success": False,
                    "error": str(exc),
                },
            )
            self._set_task_status(task=trace_task, status="failed")
            raise

    def _send_via_whatsapp_api(self, *, client_key: str, text: str, trace_task_id: str) -> dict[str, Any]:
        if self.sandbox_mode:
            payload = {"delivery": "simulated", "status": "sent", "sandbox": True}
            self._emit_task_event(
                task_id=trace_task_id,
                event_type="whatsapp_sandbox_mode",
                summary="WhatsApp sandbox activo: envio simulado",
                payload={"client_key": client_key, "text": text, "sandbox": True},
            )
            return payload
        if self.api_client is not None:
            response = self.api_client.post(
                "/whatsapp/send",
                json={"phone_number": client_key, "text": text},
            )
            if response.status_code != 200:
                raise RuntimeError(f"whatsapp_send_failed:{response.status_code}:{response.text}")
            payload = response.json()
            return payload if isinstance(payload, dict) else {"delivery": "real", "status": "sent"}
        try:
            gateway_url = (settings.openclaw_gateway_url or "http://127.0.0.1:18797").rstrip("/")
            with httpx.Client(base_url=gateway_url, timeout=15.0) as client:
                response = client.post(
                    "/whatsapp/send",
                    json={"phone_number": client_key, "text": text},
                )
            if response.status_code == 200:
                payload = response.json()
                return payload if isinstance(payload, dict) else {"delivery": "real", "status": "sent"}
        except Exception:
            # Fallback al CLI real de OpenClaw cuando el endpoint HTTP no esta disponible.
            pass

        cli_path = self._resolve_openclaw_cli()
        cli_env = dict(os.environ)
        if "/" in cli_path:
            cli_dir = str(Path(cli_path).parent)
            cli_env["PATH"] = f"{cli_dir}:{cli_env.get('PATH', '')}"
        config_path = (settings.openclaw_config_path or "").strip()
        if config_path:
            cli_env["OPENCLAW_CONFIG_PATH"] = config_path
        state_dir = (settings.openclaw_state_dir or "").strip()
        if state_dir:
            cli_env["OPENCLAW_STATE_DIR"] = state_dir
        gateway_url = (settings.openclaw_gateway_url or "").strip()
        if gateway_url:
            cli_env["OPENCLAW_GATEWAY_URL"] = gateway_url
        gateway_token = (getattr(settings, "openclaw_gateway_token", "") or "").strip()
        if gateway_token:
            cli_env["OPENCLAW_GATEWAY_TOKEN"] = gateway_token

        completed = subprocess.run(
            [
                cli_path,
                "message",
                "send",
                "--channel",
                "whatsapp",
                "--account",
                "default",
                "--target",
                client_key,
                "--message",
                text,
                "--json",
            ],
            check=False,
            capture_output=True,
            text=False,
            env=cli_env,
        )
        stdout_text = (completed.stdout or b"").decode("utf-8", errors="replace")
        stderr_text = (completed.stderr or b"").decode("utf-8", errors="replace")
        if completed.returncode != 0:
            output_tail = (stderr_text or stdout_text or "").strip()
            raise RuntimeError(f"whatsapp_send_failed_cli:{output_tail}")
        lines = [line.strip() for line in stdout_text.splitlines() if line.strip()]
        if not lines:
            return {"delivery": "real", "status": "sent", "transport": "openclaw-cli"}
        for raw in reversed(lines):
            if not raw.startswith("{"):
                continue
            try:
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    return payload
            except Exception:
                continue
        return {"delivery": "real", "status": "sent", "transport": "openclaw-cli", "raw": lines[-1]}

    def _resolve_openclaw_cli(self) -> str:
        explicit = (getattr(settings, "openclaw_cli_path", "") or "").strip()
        if explicit and Path(explicit).exists():
            return explicit
        if Path("/mnt/nvm/versions/node").exists():
            matches = sorted(Path("/mnt/nvm/versions/node").glob("*/bin/openclaw"))
            for candidate in reversed(matches):
                if candidate.exists():
                    return str(candidate)
        return "openclaw"

    def _extract_client_key(self, phone_number: str) -> str:
        cleaned = (phone_number or "").strip()
        if not cleaned:
            raise ValueError("phone_number_required")
        if not re.fullmatch(r"\+521\d{10}", cleaned):
            raise ValueError("phone_number_invalid_format_expected_+521XXXXXXXXXX")
        return cleaned

    def _parse_allowed_numbers(self, raw_value: str) -> set[str]:
        numbers = set()
        for token in (raw_value or "").split(","):
            normalized = token.strip()
            if normalized:
                numbers.add(normalized)
        return numbers

    def _validate_safelist(self, *, client_key: str, trace_task_id: str, direction: str) -> None:
        # Empty safelist means "allow all clients" for production rollout.
        if not self.allowed_numbers:
            return
        if client_key in self.allowed_numbers:
            return
        self._emit_task_event(
            task_id=trace_task_id,
            event_type="whatsapp_security_block",
            summary="WhatsApp security block por numero fuera de safelist",
            payload={"client_key": client_key, "direction": direction, "allowed_numbers": sorted(self.allowed_numbers)},
        )
        raise PermissionError(f"phone_number_not_allowed:{client_key}")

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

    def _set_task_status(self, *, task: Task, status: str) -> None:
        task.status = status
        task.updated_at = datetime.now(UTC)
        self.session.add(task)
        self.session.commit()
