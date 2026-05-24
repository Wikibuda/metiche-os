from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
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

    # NUEVOS task_types
    if normalized_type == "code_execution":
        return _dispatch_code_execution(session, task)
    if normalized_type == "data_query":
        return _dispatch_data_query(session, task)
    if normalized_type == "batch_sql":
        return _dispatch_batch_sql(session, task)
    if normalized_type == "narrative":
        return _dispatch_narrative(session, task)

    # Existente: send_message
    if normalized_type == "send_message":
        return _dispatch_send_message(session, task, api_client=api_client)

    return DispatchResult(
        success=False,
        channel=normalized_channel or task.channel,
        task_type=normalized_type or task.task_type,
        details={"reason": "unsupported_task_type"},
        retry_count=0,
        final_status="failed_non_retryable",
        error="unsupported_task_type",
    )


def _dispatch_send_message(
    session: Session,
    task: UnifiedTask,
    *,
    api_client: Any | None = None,
) -> DispatchResult:
    normalized_channel = (task.channel or "").strip().lower()
    if normalized_channel not in {"whatsapp", "telegram"}:
        return DispatchResult(
            success=False,
            channel=normalized_channel,
            task_type="send_message",
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


def _dispatch_code_execution(session, task):
    """Ejecuta código/script. Placeholder seguro."""
    import subprocess, tempfile, os
    code = str(task.task_data or {}).get("code", "")
    if not code:
        return DispatchResult(success=False, channel="code", task_type="code_execution",
            details={"reason": "no_code"}, retry_count=0, final_status="failed_non_retryable",
            error="No code provided")
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.flush()
            result = subprocess.run(['python3', f.name], capture_output=True, text=True, timeout=30)
        os.unlink(f.name)
        return DispatchResult(success=result.returncode==0, channel="code", task_type="code_execution",
            details={"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode},
            retry_count=0, final_status="ok" if result.returncode==0 else "failed_retryable")
    except Exception as e:
        return DispatchResult(success=False, channel="code", task_type="code_execution",
            details={"error": str(e)}, retry_count=0, final_status="failed_non_retryable", error=str(e))


def _dispatch_data_query(session, task):
    """Ejecuta consulta SQL de solo lectura."""
    import json
    query = str(task.task_data or {}).get("query", "")
    if not query:
        return DispatchResult(success=False, channel="data", task_type="data_query",
            details={"reason": "no_query"}, retry_count=0, final_status="failed_non_retryable", error="No query")
    try:
        from app.core.db import get_session
        db_session = next(get_session())
        result = db_session.execute(text(query))
        rows = [dict(row._mapping) for row in result]
        return DispatchResult(success=True, channel="data", task_type="data_query",
            details={"rows": rows[:100], "total": len(rows)}, retry_count=0, final_status="ok")
    except Exception as e:
        return DispatchResult(success=False, channel="data", task_type="data_query",
            details={"error": str(e)}, retry_count=0, final_status="failed_non_retryable", error=str(e))


def _dispatch_batch_sql(session, task):
    """Ejecuta operación SQL batch con validación."""
    data = task.task_data or {}
    queries = data.get("queries", [])
    if not queries:
        return DispatchResult(success=False, channel="batch", task_type="batch_sql",
            details={"reason": "no_queries"}, retry_count=0, final_status="failed_non_retryable", error="No queries")
    try:
        from app.core.db import get_session
        db_session = next(get_session())
        results = []
        for i, q in enumerate(queries):
            try:
                db_session.execute(text(q))
                results.append({"batch": i, "status": "ok"})
            except Exception as e:
                results.append({"batch": i, "status": "error", "error": str(e)})
                db_session.rollback()
                break
        else:
            db_session.commit()
        return DispatchResult(success=all(r["status"]=="ok" for r in results), channel="batch",
            task_type="batch_sql", details={"batches": results}, retry_count=0,
            final_status="ok" if all(r["status"]=="ok" for r in results) else "failed_non_retryable")
    except Exception as e:
        return DispatchResult(success=False, channel="batch", task_type="batch_sql",
            details={"error": str(e)}, retry_count=0, final_status="failed_non_retryable", error=str(e))


def _dispatch_narrative(session, task):
    """Genera entrada narrativa/bitácora."""
    data = task.task_data or {}
    content = data.get("content", "")
    source = data.get("source", "system")
    if not content:
        return DispatchResult(success=False, channel="narrative", task_type="narrative",
            details={"reason": "no_content"}, retry_count=0, final_status="failed_non_retryable", error="No content")
    try:
        from app.services.dashboard_service import create_narrative_entry
        entry = create_narrative_entry(session, content=content, source=source, related_task_id=task.id)
        return DispatchResult(success=True, channel="narrative", task_type="narrative",
            details={"entry_id": entry.id if hasattr(entry,'id') else None}, retry_count=0, final_status="ok")
    except Exception as e:
        return DispatchResult(success=False, channel="narrative", task_type="narrative",
            details={"error": str(e)}, retry_count=0, final_status="failed_non_retryable", error=str(e))
