from __future__ import annotations

import asyncio
import glob
import json
import logging
import time
from pathlib import Path
from typing import Any

from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.services.openclaw_session_resolver import OpenClawSessionOutboundResolver
from app.services.whatsapp_event_recorder import (
    outbound_event_exists_by_correlation_id,
    record_whatsapp_outbound_event,
)

logger = logging.getLogger(__name__)


class OpenClawAutoReplyPoller:
    def __init__(self) -> None:
        self._state_path = Path(settings.openclaw_autoreply_state_path)
        self._poll_seconds = max(1, int(settings.openclaw_autoreply_poll_seconds))
        self._log_glob = settings.openclaw_autoreply_log_glob
        self._backfill_on_start = bool(settings.openclaw_autoreply_backfill_on_start)
        self._session_resolver = self._build_session_resolver()
        self._state = self._load_state()
        self._initialized_files: set[str] = set()

    async def run_forever(self) -> None:
        logger.info(
            "OpenClaw auto-reply poller enabled (glob=%s, poll_seconds=%s)",
            self._log_glob,
            self._poll_seconds,
        )
        while True:
            try:
                self._poll_once()
            except Exception:
                logger.exception("OpenClaw auto-reply poller iteration failed")
            await asyncio.sleep(self._poll_seconds)

    def _poll_once(self) -> None:
        log_paths = sorted(glob.glob(self._log_glob))
        if not log_paths:
            return

        changed = False
        for path in log_paths:
            changed = self._consume_file(path) or changed

        self._prune_seen(max_items=5000)
        if changed:
            self._save_state()

    def _consume_file(self, path: str) -> bool:
        file_path = Path(path)
        if not file_path.exists() or not file_path.is_file():
            return False

        stat = file_path.stat()
        inode = int(stat.st_ino)
        size = int(stat.st_size)
        state_files = self._state.setdefault("files", {})
        file_state = state_files.get(path, {})
        previous_inode = int(file_state.get("inode", -1))
        previous_position = int(file_state.get("position", 0))

        if previous_inode != inode:
            start_position = 0 if self._backfill_on_start else size
        elif previous_position > size:
            start_position = 0
        else:
            start_position = previous_position

        # On first seen file in this process, default to tailing new lines only.
        if path not in self._initialized_files and not self._backfill_on_start and not file_state:
            start_position = size

        processed = False
        with file_path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(start_position)
            for raw_line in handle:
                line = raw_line.rstrip("\n")
                if self._handle_line(line):
                    processed = True
            end_position = handle.tell()

        state_changed = (
            previous_inode != inode
            or previous_position != end_position
            or path not in self._initialized_files
            or processed
        )
        state_files[path] = {"inode": inode, "position": end_position}
        self._initialized_files.add(path)
        return state_changed

    def _handle_line(self, line: str) -> bool:
        lowered = line.lower()
        if "web-auto-reply" not in lowered or "auto-reply sent" not in lowered:
            return False

        payload = self._extract_autoreply_payload(line)
        if not payload:
            return False

        correlation_id = str(payload.get("correlationId") or "").strip()
        if correlation_id and self._seen(correlation_id):
            return False

        event_timestamp = line.split(" ", 1)[0] if " " in line else None
        resolved = self._resolve_from_session(
            to_value=str(payload.get("to") or ""),
            event_timestamp=event_timestamp,
        )
        message_text = resolved["text"] if resolved else payload.get("text")
        source_label = "openclaw_session_resolved" if resolved else "openclaw_log_autoreply"

        outbound_payload = {
            "timestamp": event_timestamp,
            "channel": "whatsapp",
            "event_type": "message:sent",
            "to": payload.get("to"),
            "text": message_text,
            "bot_name": settings.openclaw_autoreply_sender_name,
            "source": source_label,
            "correlation_id": correlation_id or None,
            "raw_payload": payload,
            "session_resolution": resolved,
        }

        with Session(engine) as session:
            if correlation_id and outbound_event_exists_by_correlation_id(session, correlation_id):
                self._mark_seen(correlation_id)
                return False
            try:
                record_whatsapp_outbound_event(
                    session,
                    raw_payload=outbound_payload,
                    source_label=source_label,
                    default_sender_name=settings.openclaw_autoreply_sender_name,
                    summary=(
                        "Sesion OpenClaw resolvio texto outbound completo"
                        if resolved
                        else "Log OpenClaw detecto respuesta saliente de web-auto-reply"
                    ),
                )
            except ValueError:
                return False

        if correlation_id:
            self._mark_seen(correlation_id)
        return True

    def _build_session_resolver(self) -> OpenClawSessionOutboundResolver | None:
        if not bool(settings.openclaw_session_resolver_enabled):
            return None
        session_globs = [
            item.strip()
            for item in str(settings.openclaw_session_globs).split(",")
            if item.strip()
        ]
        if not session_globs:
            return None
        return OpenClawSessionOutboundResolver(
            session_globs=session_globs,
            max_files=int(settings.openclaw_session_resolver_max_files),
            max_lines_per_file=int(settings.openclaw_session_resolver_max_lines_per_file),
            max_delta_seconds=int(settings.openclaw_session_resolver_max_delta_seconds),
        )

    def _resolve_from_session(self, *, to_value: str, event_timestamp: str | None) -> dict[str, Any] | None:
        resolver = self._session_resolver
        if resolver is None:
            return None
        try:
            match = resolver.resolve(to_phone=to_value, event_timestamp=event_timestamp)
        except Exception:
            logger.exception("OpenClaw session resolution failed")
            return None
        if match is None:
            return None
        return {
            "resolved": True,
            "session_file": match.session_file,
            "session_timestamp": match.session_timestamp,
            "delta_ms": match.delta_ms,
            "source_kind": match.source_kind,
            "text": match.text,
        }

    def _extract_autoreply_payload(self, line: str) -> dict[str, Any] | None:
        objects = self._extract_json_objects(line)
        for obj in objects:
            candidate = self._find_payload_candidate(obj)
            if candidate is not None:
                return candidate
        return None

    def _find_payload_candidate(self, node: Any) -> dict[str, Any] | None:
        if isinstance(node, dict):
            to_value = node.get("to")
            text_value = node.get("text")
            if isinstance(to_value, str) and isinstance(text_value, str):
                return node
            for value in node.values():
                found = self._find_payload_candidate(value)
                if found is not None:
                    return found
            return None
        if isinstance(node, list):
            for value in node:
                found = self._find_payload_candidate(value)
                if found is not None:
                    return found
        return None

    def _extract_json_objects(self, line: str) -> list[Any]:
        objects: list[Any] = []
        decoder = json.JSONDecoder()
        idx = 0
        length = len(line)
        while idx < length:
            brace = line.find("{", idx)
            if brace < 0:
                break
            try:
                parsed, end = decoder.raw_decode(line, brace)
            except Exception:
                idx = brace + 1
                continue
            objects.append(parsed)
            idx = max(end, brace + 1)
        return objects

    def _seen(self, correlation_id: str) -> bool:
        return correlation_id in self._state.setdefault("seen_ids", {})

    def _mark_seen(self, correlation_id: str) -> None:
        self._state.setdefault("seen_ids", {})[correlation_id] = time.time()

    def _prune_seen(self, *, max_items: int) -> None:
        seen = self._state.setdefault("seen_ids", {})
        if len(seen) <= max_items:
            return
        ordered = sorted(seen.items(), key=lambda item: float(item[1]))
        for key, _ in ordered[: len(seen) - max_items]:
            seen.pop(key, None)

    def _load_state(self) -> dict[str, Any]:
        try:
            if self._state_path.exists():
                data = json.loads(self._state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data.setdefault("files", {})
                    data.setdefault("seen_ids", {})
                    return data
        except Exception:
            logger.exception("Could not load OpenClaw auto-reply poller state")
        return {"files": {}, "seen_ids": {}}

    def _save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(self._state), encoding="utf-8")
