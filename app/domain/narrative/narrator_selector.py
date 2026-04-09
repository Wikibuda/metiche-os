from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import Session
from app.domain.narrative.models import NarrativeEntryCreate
from app.domain.narrative.service import create_narrative_entry


@dataclass
class NarratorSelectorConfig:
    high_importance_levels: tuple[str, ...] = ("high", "critical")
    wonder_threshold: int = 3
    selector_version: str = "minimal-v0"
    max_events_per_tick: int = 100
    narrator_code: str = "metiche"


class MinimalNarratorSelector:
    """
    Minimal standalone selector design.

    It scans `task_events` and creates `narrative_candidates` for events that:
    - have high/critical importance, or
    - have wonder_level above the configured threshold.

    This class is intentionally not wired into worker/runtime loops yet.
    """

    def __init__(self, config: NarratorSelectorConfig | None = None) -> None:
        self.config = config or NarratorSelectorConfig()

    def tick(self, session: Session) -> int:
        """Run one selector cycle and return inserted candidate count."""
        events = self._load_eligible_events(session)
        inserted = 0
        for event in events:
            if self._candidate_exists(session, event["id"]):
                continue
            self._insert_candidate(session, event)
            inserted += 1
        if inserted:
            session.commit()
        return inserted

    def promote_pending_candidates(self, session: Session, limit: int = 100) -> int:
        """Promote pending candidates into narrative entries and daily collections."""
        safe_limit = max(1, min(limit, 500))
        pending = self._load_pending_candidates(session, safe_limit)
        promoted = 0
        for candidate in pending:
            entry = create_narrative_entry(
                session,
                NarrativeEntryCreate(
                    title=candidate["title"],
                    body=candidate["body"],
                    narrative_type=candidate["narrative_type"],
                    wonder_level=max(1, min(int(candidate["wonder_level"]), 5)),
                    narrator_code=self.config.narrator_code,
                ),
            )
            collection_id = self._upsert_daily_collection(session, entry.created_at.date())
            self._append_collection_item(session, collection_id=collection_id, narrative_entry_id=entry.id)
            self._mark_candidate_published(session, candidate["id"])
            promoted += 1
        if promoted:
            session.commit()
        return promoted

    def _load_eligible_events(self, session: Session) -> list[dict]:
        levels = ", ".join([f"'{lvl}'" for lvl in self.config.high_importance_levels])
        sql = text(
            f"""
            SELECT
                id,
                event_type,
                event_summary,
                importance_level,
                wonder_level,
                payload_json,
                occurred_at
            FROM task_events
            WHERE importance_level IN ({levels})
               OR wonder_level > :wonder_threshold
            ORDER BY occurred_at DESC
            LIMIT :limit
            """
        )
        conn = session.connection()
        rows = conn.execute(
            sql,
            {"wonder_threshold": self.config.wonder_threshold, "limit": self.config.max_events_per_tick},
        ).fetchall()
        return [dict(row._mapping) for row in rows]

    def _candidate_exists(self, session: Session, task_event_id: str) -> bool:
        sql = text("SELECT id FROM narrative_candidates WHERE task_event_id = :task_event_id LIMIT 1")
        conn = session.connection()
        return conn.execute(sql, {"task_event_id": task_event_id}).first() is not None

    def _insert_candidate(self, session: Session, event: dict) -> None:
        payload_preview = self._payload_preview(event.get("payload_json"))
        wonder_level = self._resolve_wonder_level_for_event(event)
        title = f"[{event['event_type']}] {event['event_summary'][:70]}".strip()
        body = "\n".join(
            [
                f"Evento: {event['event_type']}",
                f"Importancia: {event['importance_level']}",
                f"Asombro: {wonder_level}",
                f"Ocurrio: {event['occurred_at']}",
                f"Resumen: {event['event_summary']}",
                f"Payload: {payload_preview}",
            ]
        )
        reason = (
            "importance_high"
            if event["importance_level"] in self.config.high_importance_levels
            else f"wonder_gt_{self.config.wonder_threshold}"
        )
        sql = text(
            """
            INSERT INTO narrative_candidates (
                id,
                task_event_id,
                title,
                body,
                narrative_type,
                wonder_level,
                selector_reason,
                selector_version,
                status,
                created_at
            ) VALUES (
                :id,
                :task_event_id,
                :title,
                :body,
                :narrative_type,
                :wonder_level,
                :selector_reason,
                :selector_version,
                :status,
                :created_at
            )
            """
        )
        conn = session.connection()
        conn.execute(
            sql,
            {
                "id": str(uuid4()),
                "task_event_id": event["id"],
                "title": title or "Evento relevante",
                "body": body,
                "narrative_type": "chronicle",
                "wonder_level": max(1, int(wonder_level)),
                "selector_reason": reason,
                "selector_version": self.config.selector_version,
                "status": "pending",
                "created_at": datetime.utcnow(),
            },
        )

    def _load_pending_candidates(self, session: Session, limit: int) -> list[dict]:
        sql = text(
            """
            SELECT id, title, body, narrative_type, wonder_level, created_at
            FROM narrative_candidates
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT :limit
            """
        )
        conn = session.connection()
        rows = conn.execute(sql, {"limit": limit}).fetchall()
        return [dict(row._mapping) for row in rows]

    def _upsert_daily_collection(self, session: Session, day: date) -> str:
        collection_key = f"daily-{day.isoformat()}"
        conn = session.connection()
        existing = conn.execute(
            text("SELECT id FROM narrative_collections WHERE collection_key = :collection_key LIMIT 1"),
            {"collection_key": collection_key},
        ).first()
        if existing:
            return existing[0]
        collection_id = str(uuid4())
        conn.execute(
            text(
                """
                INSERT INTO narrative_collections (
                    id, collection_key, collection_type, title, description, curator_code, status, created_at
                ) VALUES (
                    :id, :collection_key, :collection_type, :title, :description, :curator_code, :status, :created_at
                )
                """
            ),
            {
                "id": collection_id,
                "collection_key": collection_key,
                "collection_type": "daily",
                "title": f"Cronicas del {day.isoformat()}",
                "description": "Coleccion diaria generada por narrator_selector.",
                "curator_code": self.config.narrator_code,
                "status": "open",
                "created_at": datetime.utcnow(),
            },
        )
        return collection_id

    def _append_collection_item(self, session: Session, collection_id: str, narrative_entry_id: str) -> None:
        conn = session.connection()
        next_order_row = conn.execute(
            text("SELECT COALESCE(MAX(item_order), 0) + 1 FROM narrative_collection_items WHERE collection_id = :collection_id"),
            {"collection_id": collection_id},
        ).first()
        next_order = int(next_order_row[0]) if next_order_row else 1
        conn.execute(
            text(
                """
                INSERT INTO narrative_collection_items (
                    id, collection_id, narrative_entry_id, item_order, include_reason, created_at
                ) VALUES (
                    :id, :collection_id, :narrative_entry_id, :item_order, :include_reason, :created_at
                )
                """
            ),
            {
                "id": str(uuid4()),
                "collection_id": collection_id,
                "narrative_entry_id": narrative_entry_id,
                "item_order": next_order,
                "include_reason": "selector_auto_promote",
                "created_at": datetime.utcnow(),
            },
        )

    def _mark_candidate_published(self, session: Session, candidate_id: str) -> None:
        conn = session.connection()
        conn.execute(
            text(
                """
                UPDATE narrative_candidates
                SET status = 'published', selected_at = :selected_at
                WHERE id = :candidate_id
                """
            ),
            {"candidate_id": candidate_id, "selected_at": datetime.utcnow()},
        )

    @staticmethod
    def _payload_preview(payload_json: str | None, max_len: int = 240) -> str:
        if not payload_json:
            return "{}"
        try:
            payload_obj = json.loads(payload_json)
            normalized = json.dumps(payload_obj, ensure_ascii=False)
        except json.JSONDecodeError:
            normalized = payload_json
        if len(normalized) <= max_len:
            return normalized
        return normalized[: max_len - 3] + "..."

    @staticmethod
    def _resolve_wonder_level_for_event(event: dict) -> int:
        if event.get("event_type") != "validation_attempt":
            return int(event.get("wonder_level", 3))
        payload_json = event.get("payload_json")
        if not payload_json:
            return 3
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            return 3
        passed = bool(payload.get("passed"))
        critical = bool(payload.get("critical"))
        if not passed and critical:
            return 5
        if passed:
            return 4
        return 3
