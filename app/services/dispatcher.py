from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session

from app.integrations.telegram_adapter import OutboundTelegramMessage, TelegramAdapter
from app.integrations.whatsapp_adapter import OutboundWhatsAppMessage, WhatsAppAdapter


@dataclass
class UnifiedTask:
    task_type: str
    channel: str
    client_key: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DispatchResult:
    success: bool
    channel: str
    task_type: str
    details: dict[str, Any]
    retry_count: int = 0
    final_status: str = "failed"
    error: str | None = None


RETRY_BACKOFF_SECONDS = (1, 2, 4)
MAX_RETRIES = 3


def _classify_dispatch_exception(exc: Exception) -> str:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return "retryable"
    error_text = str(exc).strip().lower()
    retryable_hints = (
        "timeout",
        "timed out",
        "connection",
        "temporarily unavailable",
        "network unreachable",
        "connection reset",
    )
    if any(hint in error_text for hint in retryable_hints):
        return "retryable"
    non_retryable_hints = (
        "unauthorized",
        "forbidden",
        "authentication",
        "auth",
        "invalid number",
        "phone_number_invalid",
        "invalid_phone",
        "invalid_telegram_chat_id",
        "chat_id_not_allowed",
    )
    if any(hint in error_text for hint in non_retryable_hints):
        return "non_retryable"
    return "non_retryable"


def dispatch_unified_task(
    session: Session,
    task: UnifiedTask,
    *,
    api_client: Any | None = None,
) -> DispatchResult:
    normalized_channel = (task.channel or "").strip().lower()
    normalized_type = (task.task_type or "").strip().lower()
    if normalized_type != "send_message":
        return DispatchResult(
            success=False,
            channel=normalized_channel or task.channel,
            task_type=normalized_type or task.task_type,
            details={"reason": "unsupported_task_type"},
            retry_count=0,
            final_status="failed_non_retryable",
            error="unsupported_task_type",
        )
    if normalized_channel not in {"whatsapp", "telegram"}:
        return DispatchResult(
            success=False,
            channel=normalized_channel,
            task_type=normalized_type,
            details={"reason": "unsupported_channel"},
            retry_count=0,
            final_status="failed_non_retryable",
            error="unsupported_channel",
        )
    if normalized_channel == "telegram":
        adapter: Any = TelegramAdapter(session=session, api_client=api_client)
        outbound_payload: Any = OutboundTelegramMessage(client_key=task.client_key, text=task.message)
    else:
        adapter = WhatsAppAdapter(session=session, api_client=api_client)
        outbound_payload = OutboundWhatsAppMessage(client_key=task.client_key, text=task.message)
    retry_count = 0
    errors: list[dict[str, Any]] = []
    while True:
        try:
            payload = adapter.send_message(outbound_payload)
            return DispatchResult(
                success=bool(payload.get("success")),
                channel=normalized_channel,
                task_type="send_message",
                details={"payload": payload, "metadata": task.metadata, "errors": errors},
                retry_count=retry_count,
                final_status="succeeded",
                error=None,
            )
        except Exception as exc:
            classification = _classify_dispatch_exception(exc)
            errors.append(
                {
                    "attempt": retry_count + 1,
                    "classification": classification,
                    "error": str(exc),
                }
            )
            if classification != "retryable":
                return DispatchResult(
                    success=False,
                    channel=normalized_channel,
                    task_type="send_message",
                    details={"metadata": task.metadata, "errors": errors},
                    retry_count=retry_count,
                    final_status="failed_non_retryable",
                    error=f"dispatch_exception:{exc}",
                )
            if retry_count >= MAX_RETRIES:
                return DispatchResult(
                    success=False,
                    channel=normalized_channel,
                    task_type="send_message",
                    details={"metadata": task.metadata, "errors": errors},
                    retry_count=retry_count,
                    final_status="failed_retryable_exhausted",
                    error=f"dispatch_exception:{exc}",
                )
            backoff = RETRY_BACKOFF_SECONDS[min(retry_count, len(RETRY_BACKOFF_SECONDS) - 1)]
            time.sleep(backoff)
            retry_count += 1
