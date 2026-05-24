"""
Plane Notifier — Bot de Telegram para notificar eventos de Plane.

Eventos que notifica:
  1. Issues nuevos con label `run:enjambre`
  2. Issues completados
  3. Cuando un Viewer necesita aprobación

Usa subprocess para llamar `openclaw message send` y enviar mensajes
a un chat de Telegram configurable.

Configuración (settings / env vars):
  TELEGRAM_CHAT_ID   → ID del chat de Telegram donde enviar notificaciones
  NOTIFY_ON_COMPLETE → bool (default True)
  NOTIFY_ON_NEW_ISSUE → bool (default True)
  NOTIFY_ON_VIEWER_NEEDS_APPROVAL → bool (default True)

Uso:
  from app.services.plane_notifier import notify_new_issue, notify_issue_completed, ...
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from typing import Any


# ── Configuración desde environment/settings ─────────────────────────────

def _get_chat_id() -> str:
    """Retorna el chat ID desde env o fallback."""
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip() or "1230372781"  # Gus por defecto


def _should_notify(key: str) -> bool:
    """Verifica si un tipo de notificación está habilitado."""
    raw = os.environ.get(key, "true").strip().lower()
    return raw not in ("false", "0", "no", "off")


def _notify_on_complete() -> bool:
    return _should_notify("NOTIFY_ON_COMPLETE")


def _notify_on_new_issue() -> bool:
    return _should_notify("NOTIFY_ON_NEW_ISSUE")


def _notify_on_viewer_approval() -> bool:
    return _should_notify("NOTIFY_ON_VIEWER_NEEDS_APPROVAL")


# ── Envío de mensajes por Telegram ──────────────────────────────────────

def _call_openclaw_message(text: str, chat_id: str | None = None) -> bool:
    """
    Envía un mensaje de Telegram vía `openclaw message send`.

    Retorna True si se envió exitosamente, False en caso contrario.
    """
    target = chat_id or _get_chat_id()
    if not target:
        return False

    try:
        result = subprocess.run(
            [
                "openclaw", "message", "send",
                "--channel", "telegram",
                "--target", target,
                "--message", text,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Fallback silencioso si falla openclaw command
            return False
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _format_issue(
    title: str,
    issue_id: str,
    state: str | None = None,
    labels: list[str] | None = None,
    url: str | None = None,
) -> str:
    """Formatea un issue de Plane como texto para Telegram."""
    lines = [f"📌 *{title}*"]
    lines.append(f"  🆔 `{issue_id}`")
    if state:
        emoji = "✅" if state.lower() in ("done", "completed", "closed") else "🔄"
        lines.append(f"  {emoji} Estado: {state}")
    if labels:
        labels_str = " · ".join(f"`{l}`" for l in labels)
        lines.append(f"  🏷 {labels_str}")
    if url:
        lines.append(f"  🔗 {url}")
    return "\n".join(lines)


# ── Funciones públicas ──────────────────────────────────────────────────


def notify_new_issue(
    title: str,
    issue_id: str,
    labels: list[str] | None = None,
    url: str | None = None,
    chat_id: str | None = None,
) -> bool:
    """
    Notifica un issue nuevo en Plane.

    Args:
        title: Título del issue.
        issue_id: ID del issue en Plane.
        labels: Labels del issue (ej: ["run:enjambre", "bug"]).
        url: URL directa al issue en Plane.
        chat_id: Chat ID de Telegram (opcional, usa default si no se pasa).

    Returns: True si se envió la notificación.
    """
    if not _notify_on_new_issue():
        return False

    is_swarm = labels and any("enjambre" in (l or "").lower() for l in labels)

    header = "🐝 *Nuevo issue enjambre*" if is_swarm else "📋 *Nuevo issue en Plane*"
    body = _format_issue(title, issue_id, labels=labels, url=url)

    text = f"{header}\n\n{body}"
    return _call_openclaw_message(text, chat_id)


def notify_issue_completed(
    title: str,
    issue_id: str,
    summary: str | None = None,
    url: str | None = None,
    chat_id: str | None = None,
) -> bool:
    """
    Notifica que un issue de Plane fue completado.

    Args:
        title: Título del issue.
        issue_id: ID del issue en Plane.
        summary: Resumen opcional del resultado.
        url: URL directa.
        chat_id: Chat ID de Telegram (opcional).

    Returns: True si se envió la notificación.
    """
    if not _notify_on_complete():
        return False

    header = "✅ *Issue completado*"
    body = _format_issue(title, issue_id, state="completed", url=url)
    if summary:
        body += f"\n\n📝 {summary}"

    text = f"{header}\n\n{body}"
    return _call_openclaw_message(text, chat_id)


def notify_viewer_needs_approval(
    title: str,
    issue_id: str,
    viewer: str | None = None,
    url: str | None = None,
    chat_id: str | None = None,
) -> bool:
    """
    Notifica que un Viewer necesita aprobación en un issue.

    Args:
        title: Título del issue.
        issue_id: ID del issue en Plane.
        viewer: Nombre del viewer que requiere aprobación.
        url: URL directa.
        chat_id: Chat ID de Telegram (opcional).

    Returns: True si se envió la notificación.
    """
    if not _notify_on_viewer_approval():
        return False

    header = "👀 *Requiere aprobación*"
    body = _format_issue(title, issue_id, url=url)
    if viewer:
        body += f"\n  👤 Viewer: {viewer}"

    text = f"{header}\n\n{body}"
    return _call_openclaw_message(text, chat_id)


def notify_custom(
    message: str,
    chat_id: str | None = None,
) -> bool:
    """
    Envía un mensaje personalizado al chat configurado.
    Útil para pruebas o notificaciones ad-hoc.
    """
    return _call_openclaw_message(message, chat_id)


def notify_issue_update(
    title: str,
    issue_id: str,
    old_state: str,
    new_state: str,
    labels: list[str] | None = None,
    url: str | None = None,
    chat_id: str | None = None,
) -> bool:
    """
    Notifica un cambio de estado en un issue de Plane.

    Args:
        title: Título del issue.
        issue_id: ID del issue en Plane.
        old_state: Estado anterior.
        new_state: Estado nuevo.
        labels: Labels del issue.
        url: URL directa.
        chat_id: Chat ID de Telegram (opcional).

    Returns: True si se envió la notificación.
    """
    if old_state == new_state:
        return False

    header = "🔄 *Issue actualizado*"
    body = _format_issue(title, issue_id, state=new_state, labels=labels, url=url)
    body += f"\n  📊 {old_state} → {new_state}"

    text = f"{header}\n\n{body}"
    return _call_openclaw_message(text, chat_id)


def notify_error(
    issue_id: str,
    title: str,
    error_message: str,
    url: str | None = None,
    chat_id: str | None = None,
) -> bool:
    """
    Notifica un error relacionado con un issue de Plane.
    """
    header = "❌ *Error en issue*"
    body = _format_issue(title, issue_id, url=url)
    body += f"\n\n⚠️ {error_message}"

    text = f"{header}\n\n{body}"
    return _call_openclaw_message(text, chat_id)
