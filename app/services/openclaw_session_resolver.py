from __future__ import annotations

import glob
import json
import logging
import re
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


def _normalize_phone(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) < 8:
        return None
    return f"+{digits}" if value.startswith("+") else digits


def _parse_iso8601(value: str | None) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(slots=True)
class SessionMatch:
    text: str
    session_file: str
    session_timestamp: str | None
    delta_ms: int
    source_kind: str


class OpenClawSessionOutboundResolver:
    def __init__(
        self,
        *,
        session_globs: list[str],
        max_files: int = 15,
        max_lines_per_file: int = 600,
        max_delta_seconds: int = 300,
    ) -> None:
        self._session_globs = [item for item in session_globs if item.strip()]
        self._max_files = max(1, max_files)
        self._max_lines_per_file = max(50, max_lines_per_file)
        self._max_delta_seconds = max(30, max_delta_seconds)

    def resolve(
        self,
        *,
        to_phone: str | None,
        event_timestamp: str | None,
    ) -> SessionMatch | None:
        normalized_to = _normalize_phone(to_phone)
        if not normalized_to:
            return None

        event_dt = _parse_iso8601(event_timestamp)
        if event_dt is None:
            return None

        best: SessionMatch | None = None
        for file_path in self._iter_candidate_files():
            candidate = self._scan_session_file(
                file_path=file_path,
                to_phone=normalized_to,
                event_dt=event_dt,
            )
            if candidate is None:
                continue
            if best is None or candidate.delta_ms < best.delta_ms:
                best = candidate
                if best.delta_ms == 0:
                    break
        return best

    def _iter_candidate_files(self) -> list[Path]:
        unique: dict[str, Path] = {}
        for pattern in self._session_globs:
            for raw in glob.glob(pattern):
                path = Path(raw)
                if not path.is_file():
                    continue
                unique[str(path)] = path
        if not unique:
            return []
        ordered = sorted(
            unique.values(),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        return ordered[: self._max_files]

    def _scan_session_file(
        self,
        *,
        file_path: Path,
        to_phone: str,
        event_dt: datetime,
    ) -> SessionMatch | None:
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as handle:
                lines = deque(handle, maxlen=self._max_lines_per_file)
        except Exception:
            logger.exception("Could not read OpenClaw session file: %s", file_path)
            return None

        best: SessionMatch | None = None
        active_phone: str | None = None
        for raw_line in lines:
            payload = self._parse_line(raw_line)
            if payload is None:
                continue

            active_phone = self._extract_active_phone(payload) or active_phone
            match = self._extract_message_match(
                payload=payload,
                file_path=file_path,
                to_phone=to_phone,
                event_dt=event_dt,
                active_phone=active_phone,
            )
            if match is None:
                continue
            if best is None or match.delta_ms < best.delta_ms:
                best = match
        return best

    def _parse_line(self, raw_line: str) -> dict[str, Any] | None:
        line = raw_line.strip()
        if not line:
            return None
        try:
            parsed = json.loads(line)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _extract_message_match(
        self,
        *,
        payload: dict[str, Any],
        file_path: Path,
        to_phone: str,
        event_dt: datetime,
        active_phone: str | None,
    ) -> SessionMatch | None:
        if payload.get("type") != "message":
            return None
        message = payload.get("message")
        if not isinstance(message, dict):
            return None
        if str(message.get("role") or "").strip().lower() != "assistant":
            return None

        content_items = message.get("content")
        if not isinstance(content_items, list):
            return None

        event_ts = _parse_iso8601(str(payload.get("timestamp") or ""))
        if event_ts is None:
            event_ts = _parse_iso8601(str(message.get("timestamp") or ""))
        if event_ts is None:
            return None

        best: SessionMatch | None = None
        for item in content_items:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip().lower() != "toolcall":
                continue
            if str(item.get("name") or "").strip().lower() != "message":
                continue
            args = item.get("arguments")
            if not isinstance(args, dict):
                continue

            action = str(args.get("action") or "").strip().lower()
            if action != "send":
                continue
            target = _normalize_phone(str(args.get("to") or ""))
            if not target or target != to_phone:
                continue
            text = str(args.get("message") or "").strip()
            if not text:
                continue

            delta_ms = int(abs((event_ts - event_dt).total_seconds()) * 1000)
            if delta_ms > self._max_delta_seconds * 1000:
                continue

            match = SessionMatch(
                text=text,
                session_file=str(file_path),
                session_timestamp=event_ts.isoformat(),
                delta_ms=delta_ms,
                source_kind="tool_call_message_send",
            )
            if best is None or match.delta_ms < best.delta_ms:
                best = match
        if best is not None:
            return best

        if active_phone != to_phone:
            return None
        assistant_text = self._extract_assistant_text(content_items)
        if not assistant_text:
            return None
        delta_ms = int(abs((event_ts - event_dt).total_seconds()) * 1000)
        if delta_ms > self._max_delta_seconds * 1000:
            return None
        return SessionMatch(
            text=assistant_text,
            session_file=str(file_path),
            session_timestamp=event_ts.isoformat(),
            delta_ms=delta_ms,
            source_kind="assistant_text",
        )

    def _extract_assistant_text(self, content_items: list[Any]) -> str | None:
        for item in content_items:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip().lower() != "text":
                continue
            candidate = str(item.get("text") or "").strip()
            if candidate:
                return candidate
        return None

    def _extract_active_phone(self, payload: dict[str, Any]) -> str | None:
        if payload.get("type") != "message":
            return None
        message = payload.get("message")
        if not isinstance(message, dict):
            return None
        if str(message.get("role") or "").strip().lower() != "user":
            return None
        content_items = message.get("content")
        if not isinstance(content_items, list):
            return None

        for item in content_items:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip().lower() != "text":
                continue
            text_value = str(item.get("text") or "")
            for raw_phone in re.findall(r"\+\d{8,20}", text_value):
                normalized = _normalize_phone(raw_phone)
                if normalized:
                    return normalized
        return None
