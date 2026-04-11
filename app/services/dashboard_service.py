import json
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import Session, select

from app.domain.narrative.service import list_recent_narratives
from app.domain.tasks.models import QueueEntry, Task, Validation
from app.domain.tasks.service import build_operational_overview, derive_queue_bucket, normalize_priority, run_task_flow

BOARD_STATUSES = ("queued", "running", "retrying", "failed", "done")
VALIDATOR_CHANNELS = ("telegram", "whatsapp", "shopify", "dashboard", "deepseek")
CHANNEL_STATUS_SUPPORTED = ("whatsapp", "telegram")


def map_task_status(raw_status: str) -> str:
    value = (raw_status or "").strip().lower()
    if value in {"queued", "new"}:
        return "queued"
    if value in {"deciding", "processing", "running"}:
        return "running"
    if value == "retrying":
        return "retrying"
    if value == "failed":
        return "failed"
    if value in {"validated", "done", "completed"}:
        return "done"
    if value == "cancelled":
        return "failed"
    return "queued"


def map_task_channel(task_type: str) -> str:
    value = (task_type or "").strip().lower()
    if value in {"telegram", "whatsapp", "shopify", "enjambre"}:
        return value
    if value in {"operational", "analysis", "planning"}:
        return "operational"
    return "operational"


def short_id(task_id: str) -> str:
    return (task_id or "")[:8]


def _safe_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _normalize_supported_channel(channel: str) -> str:
    normalized = (channel or "").strip().lower()
    if normalized not in CHANNEL_STATUS_SUPPORTED:
        raise ValueError("unsupported_channel")
    return normalized


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _extract_plane_issue_from_description(description: str | None) -> str | None:
    source = (description or "").strip()
    marker = "[plane_issue_id="
    if marker not in source:
        return None
    chunk = source.split(marker, 1)[1]
    issue = chunk.split("]", 1)[0].strip()
    return issue or None


def _load_plane_sync_map(session: Session, task_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not task_ids:
        return {}
    placeholders = ",".join([f":task_id_{index}" for index, _ in enumerate(task_ids)])
    params = {f"task_id_{index}": task_id for index, task_id in enumerate(task_ids)}
    try:
        rows = session.connection().execute(
            text(
                f"""
                SELECT task_id, plane_issue_id, plane_issue_url, sync_status, last_synced_at
                FROM plane_sync
                WHERE task_id IN ({placeholders})
                """
            ),
            params,
        ).fetchall()
    except Exception:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = dict(row._mapping)
        result[str(payload.get("task_id"))] = payload
    return result


def _load_latest_queue_entries(session: Session, task_ids: list[str]) -> dict[str, QueueEntry]:
    if not task_ids:
        return {}
    rows = session.exec(
        select(QueueEntry)
        .where(QueueEntry.task_id.in_(task_ids))
        .order_by(QueueEntry.enqueued_at.desc())
    ).all()
    latest: dict[str, QueueEntry] = {}
    for row in rows:
        if row.task_id in latest:
            continue
        latest[row.task_id] = row
    return latest


def _load_recent_task_events(session: Session, minutes: int = 10) -> list[dict[str, Any]]:
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    try:
        rows = session.connection().execute(
            text(
                """
                SELECT id, task_id, event_type, event_summary, importance_level, wonder_level, payload_json, occurred_at
                FROM task_events
                WHERE occurred_at >= :cutoff
                ORDER BY occurred_at DESC
                """
            ),
            {"cutoff": cutoff},
        ).fetchall()
    except Exception:
        return []
    return [dict(row._mapping) for row in rows]


def _load_channel_events(session: Session, *, channel: str, limit: int) -> list[dict[str, Any]]:
    safe_channel = _normalize_supported_channel(channel)
    safe_limit = max(1, min(limit, 100))
    try:
        rows = session.connection().execute(
            text(
                """
                SELECT id, task_id, event_type, event_summary, importance_level, wonder_level, payload_json, occurred_at
                FROM task_events
                WHERE event_type LIKE :prefix
                ORDER BY occurred_at DESC
                LIMIT :limit
                """
            ),
            {"prefix": f"{safe_channel}_%", "limit": safe_limit},
        ).fetchall()
    except Exception:
        return []
    return [dict(row._mapping) for row in rows]


def _load_latest_event(session: Session) -> datetime | None:
    try:
        row = session.connection().execute(
            text("SELECT occurred_at FROM task_events ORDER BY occurred_at DESC LIMIT 1")
        ).first()
    except Exception:
        return None
    if not row:
        return None
    return row._mapping.get("occurred_at")


def _emit_dashboard_event(session: Session, *, task_id: str, event_type: str, summary: str, payload: dict[str, Any]) -> None:
    try:
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
                "occurred_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
            },
        )
        session.commit()
    except Exception:
        session.rollback()


def get_dashboard_stats(session: Session, retrying_threshold_minutes: int = 2, blocking_threshold: int = 3) -> dict[str, Any]:
    overview = build_operational_overview(session)
    recent_events = _load_recent_task_events(session, minutes=10)

    failures_last_10m = 0
    critical_alerts = 0
    for event in recent_events:
        event_type = str(event.get("event_type") or "")
        payload = _safe_json(event.get("payload_json"))
        is_failed_validation = event_type == "validation_attempt" and not bool(payload.get("passed", True))
        is_failed_task = event_type == "task_execution_failed"
        if is_failed_validation or is_failed_task:
            failures_last_10m += 1
        if str(event.get("importance_level") or "").lower() == "critical":
            critical_alerts += 1

    now = datetime.utcnow()
    retrying_before = now - timedelta(minutes=max(1, retrying_threshold_minutes))
    retrying_old = session.exec(
        select(Task).where(Task.status == "retrying", Task.updated_at <= retrying_before)
    ).all()
    blocking_queue = session.exec(
        select(QueueEntry).where(QueueEntry.status == "queued", QueueEntry.priority == "blocking")
    ).all()

    alerts: list[dict[str, Any]] = []
    if retrying_old:
        alerts.append(
            {
                "code": "retrying_stuck",
                "severity": "critical",
                "message": f"{len(retrying_old)} tarea(s) llevan mas de {retrying_threshold_minutes} min en retrying.",
            }
        )
    if len(blocking_queue) > blocking_threshold:
        alerts.append(
            {
                "code": "blocking_queue_high",
                "severity": "critical",
                "message": f"Cola blocking alta: {len(blocking_queue)} (umbral {blocking_threshold}).",
            }
        )

    if alerts or failures_last_10m >= 3:
        system_health = "red"
    elif failures_last_10m > 0 or overview.queue_depth > 0:
        system_health = "amber"
    else:
        system_health = "green"

    return {
        "generated_at": datetime.utcnow(),
        "system_health": system_health,
        "failures_last_10m": failures_last_10m,
        "active_critical_alerts": len([item for item in alerts if item["severity"] == "critical"]) + critical_alerts,
        "last_worker_tick": _load_latest_event(session),
        "overview": overview.model_dump(),
        "alerts": alerts,
    }


def list_dashboard_tasks(
    session: Session,
    *,
    channel: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    task_id_query: str | None = None,
    limit: int = 120,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 400))
    query = select(Task).order_by(Task.updated_at.desc())
    tasks = session.exec(query).all()[:safe_limit]

    task_ids = [task.id for task in tasks]
    latest_queue_map = _load_latest_queue_entries(session, task_ids)
    plane_sync_map = _load_plane_sync_map(session, task_ids)

    rows: list[dict[str, Any]] = []
    for task in tasks:
        board_status = map_task_status(task.status)
        task_channel = map_task_channel(task.task_type)
        queue = latest_queue_map.get(task.id)
        queue_priority = normalize_priority(queue.priority) if queue else "medium"
        plane_sync = plane_sync_map.get(task.id, {})
        plane_issue_id = plane_sync.get("plane_issue_id") or _extract_plane_issue_from_description(task.description)
        plane_issue_url = plane_sync.get("plane_issue_url") or (f"plane://issues/{plane_issue_id}" if plane_issue_id else None)
        rows.append(
            {
                "task_id": task.id,
                "short_id": short_id(task.id),
                "title": task.title,
                "description": task.description,
                "status": board_status,
                "status_raw": task.status,
                "channel": task_channel,
                "priority": queue_priority,
                "execution_mode": task.execution_mode,
                "task_type": task.task_type,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "plane_issue_id": plane_issue_id,
                "plane_issue_url": plane_issue_url,
            }
        )

    filtered = rows
    if channel:
        filtered = [item for item in filtered if item["channel"] == channel]
    if status:
        filtered = [item for item in filtered if item["status"] == status]
    if priority:
        filtered = [item for item in filtered if item["priority"] == normalize_priority(priority)]
    if task_id_query:
        q = task_id_query.lower().strip()
        filtered = [item for item in filtered if q in item["task_id"].lower() or q in item["short_id"].lower()]

    grouped = {key: [] for key in BOARD_STATUSES}
    for item in filtered:
        grouped[item["status"]].append(item)

    return {
        "generated_at": datetime.utcnow(),
        "total": len(filtered),
        "tasks": filtered,
        "grouped": grouped,
    }


def get_task_detail(session: Session, task_id: str) -> dict[str, Any] | None:
    task = session.get(Task, task_id)
    if not task:
        return None

    queue_entries = session.exec(
        select(QueueEntry).where(QueueEntry.task_id == task_id).order_by(QueueEntry.enqueued_at.desc())
    ).all()
    validations = session.exec(
        select(Validation).where(Validation.task_id == task_id).order_by(Validation.created_at.desc())
    ).all()
    latest_validation = validations[0] if validations else None
    plane_sync = _load_plane_sync_map(session, [task_id]).get(task_id, {})

    try:
        event_rows = session.connection().execute(
            text(
                """
                SELECT id, task_id, execution_id, event_type, event_summary, importance_level, wonder_level, payload_json, occurred_at
                FROM task_events
                WHERE task_id = :task_id
                ORDER BY occurred_at ASC
                """
            ),
            {"task_id": task_id},
        ).fetchall()
    except Exception:
        event_rows = []

    timeline: list[dict[str, Any]] = []
    validation_results: list[dict[str, Any]] = []
    for row in event_rows:
        event = dict(row._mapping)
        payload = _safe_json(event.get("payload_json"))
        timeline.append(
            {
                "id": event.get("id"),
                "occurred_at": event.get("occurred_at"),
                "event_type": event.get("event_type"),
                "summary": event.get("event_summary"),
                "importance_level": event.get("importance_level"),
                "wonder_level": event.get("wonder_level"),
                "payload": payload,
            }
        )
        if event.get("event_type") == "validation_attempt":
            validation_results.append(payload)

    chronicle = None
    try:
        narrative = session.connection().execute(
            text(
                """
                SELECT id, title, body, created_at
                FROM narrativeentry
                WHERE title LIKE :needle
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"needle": f"%{task.title}%"},
        ).first()
        chronicle = dict(narrative._mapping) if narrative else None
    except Exception:
        chronicle = None

    return {
        "task": {
            "task_id": task.id,
            "short_id": short_id(task.id),
            "title": task.title,
            "description": task.description,
            "status": map_task_status(task.status),
            "status_raw": task.status,
            "channel": map_task_channel(task.task_type),
            "execution_mode": task.execution_mode,
            "task_type": task.task_type,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "plane_issue_id": plane_sync.get("plane_issue_id") or _extract_plane_issue_from_description(task.description),
            "plane_issue_url": plane_sync.get("plane_issue_url"),
        },
        "payload": {
            "title": task.title,
            "description": task.description,
            "execution_mode": task.execution_mode,
            "task_type": task.task_type,
        },
        "queue_entries": [
            {
                "id": entry.id,
                "priority": entry.priority,
                "queue_bucket": entry.queue_bucket,
                "status": entry.status,
                "enqueued_at": entry.enqueued_at,
                "started_at": entry.started_at,
                "completed_at": entry.completed_at,
            }
            for entry in queue_entries
        ],
        "validation": {
            "status": latest_validation.status if latest_validation else None,
            "notes": latest_validation.notes if latest_validation else None,
            "created_at": latest_validation.created_at if latest_validation else None,
            "results": validation_results,
        },
        "timeline": timeline,
        "chronicle": chronicle,
    }


def get_validator_statuses(session: Session) -> list[dict[str, Any]]:
    try:
        rows = session.connection().execute(
            text(
                """
                SELECT id, task_id, event_summary, payload_json, occurred_at
                FROM task_events
                WHERE event_type = 'validation_attempt'
                ORDER BY occurred_at DESC
                LIMIT 500
                """
            )
        ).fetchall()
    except Exception:
        rows = []

    latest_by_channel: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = dict(row._mapping)
        details = _safe_json(payload.get("payload_json"))
        channel = str(details.get("channel") or "").strip().lower()
        if not channel or channel in latest_by_channel:
            continue
        latest_by_channel[channel] = {
            "event_id": payload.get("id"),
            "task_id": payload.get("task_id"),
            "occurred_at": payload.get("occurred_at"),
            "summary": payload.get("event_summary"),
            "passed": bool(details.get("passed", False)),
            "critical": bool(details.get("critical", False)),
            "detail": details.get("detail"),
            "metadata": details.get("metadata") or {},
        }

    now = datetime.utcnow()
    stale_threshold = now - timedelta(minutes=90)
    result: list[dict[str, Any]] = []
    for channel in VALIDATOR_CHANNELS:
        attempt = latest_by_channel.get(channel)
        status = "amber"
        if attempt:
            occurred_at = _coerce_datetime(attempt.get("occurred_at"))
            if not bool(attempt.get("passed")):
                status = "red"
            elif occurred_at and occurred_at < stale_threshold:
                status = "amber"
            else:
                status = "green"
        result.append(
            {
                "channel": channel,
                "label": channel.capitalize(),
                "status": status,
                "last_check_at": attempt.get("occurred_at") if attempt else None,
                "last_attempt": attempt,
            }
        )
    return result


def get_recent_narratives_block(session: Session, limit: int = 8) -> list[dict[str, Any]]:
    rows = list_recent_narratives(session, limit=limit)
    return [
        {
            "id": row.id,
            "title": row.title,
            "body": row.body,
            "wonder_level": row.wonder_level,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def get_channel_events(session: Session, *, channel: str, limit: int = 10) -> dict[str, Any]:
    safe_channel = _normalize_supported_channel(channel)
    rows = _load_channel_events(session, channel=safe_channel, limit=limit)
    items = [
        {
            "id": row.get("id"),
            "task_id": row.get("task_id"),
            "event_type": row.get("event_type"),
            "summary": row.get("event_summary"),
            "importance_level": row.get("importance_level"),
            "wonder_level": row.get("wonder_level"),
            "occurred_at": row.get("occurred_at"),
            "payload": _safe_json(row.get("payload_json")),
        }
        for row in rows
    ]
    return {
        "generated_at": datetime.utcnow(),
        "channel": safe_channel,
        "limit": max(1, min(limit, 100)),
        "total": len(items),
        "items": items,
    }


def get_channels_status(session: Session, *, event_preview_limit: int = 5, inactivity_minutes: int = 60) -> dict[str, Any]:
    now = datetime.utcnow()
    stale_cutoff = now - timedelta(minutes=max(1, inactivity_minutes))
    channels: list[dict[str, Any]] = []

    for channel in CHANNEL_STATUS_SUPPORTED:
        rows = _load_channel_events(session, channel=channel, limit=max(3, min(event_preview_limit, 10)))
        event_types = [str(row.get("event_type") or "") for row in rows]
        last_event_at = rows[0].get("occurred_at") if rows else None
        last_event_ts = _coerce_datetime(last_event_at)
        healthy = bool(last_event_ts and last_event_ts >= stale_cutoff)
        status = "green" if healthy else "red"
        summary = {
            "total_events": len(rows),
            "memory_reads": sum(1 for event_type in event_types if event_type.endswith("_memory_read")),
            "memory_writes": sum(1 for event_type in event_types if event_type.endswith("_memory_write")),
            "send_messages": sum(1 for event_type in event_types if event_type.endswith("_send_message")),
            "sandbox_actions": sum(1 for event_type in event_types if event_type.endswith("_sandbox_mode")),
            "security_blocks": sum(1 for event_type in event_types if event_type.endswith("_security_block")),
        }
        channels.append(
            {
                "channel": channel,
                "label": channel.capitalize(),
                "status": status,
                "healthy": healthy,
                "last_event_at": last_event_at,
                "summary": summary,
                "last_events": [
                    {
                        "event_type": row.get("event_type"),
                        "summary": row.get("event_summary"),
                        "occurred_at": row.get("occurred_at"),
                    }
                    for row in rows
                ],
            }
        )

    return {
        "generated_at": now,
        "channels": channels,
    }


def run_quick_task(session: Session, *, channel: str, title: str, description: str | None, launch_swarm: bool) -> dict[str, Any]:
    from app.domain.tasks.models import TaskRunCreate

    channel_value = map_task_channel(channel)
    task_type = "enjambre" if launch_swarm else channel_value
    payload = TaskRunCreate(
        title=title.strip(),
        description=description,
        execution_mode="queued",
        task_type=task_type,
        requested_by="dashboard-operativo",
    )
    flow = run_task_flow(session, payload)
    return flow.model_dump()


def perform_task_action(session: Session, *, task_id: str, action: str, priority: str | None = None) -> dict[str, Any]:
    task = session.get(Task, task_id)
    if not task:
        raise ValueError("task_not_found")

    clean_action = (action or "").strip().lower()
    now = datetime.utcnow()

    if clean_action == "retry":
        selected_priority = normalize_priority(priority or "high")
        queue_entry = QueueEntry(
            task_id=task.id,
            priority=selected_priority,
            queue_bucket=derive_queue_bucket(selected_priority),
            status="queued",
            enqueued_at=now,
        )
        task.status = "queued"
        task.updated_at = now
        session.add(queue_entry)
        session.add(task)
        session.commit()
        _emit_dashboard_event(
            session,
            task_id=task.id,
            event_type="dashboard_retry",
            summary="Dashboard reencolo la tarea para un nuevo intento.",
            payload={"action": "retry", "priority": selected_priority},
        )
        return {"ok": True, "action": "retry", "task_id": task.id, "priority": selected_priority}

    if clean_action == "cancel":
        queued_rows = session.exec(
            select(QueueEntry).where(QueueEntry.task_id == task.id, QueueEntry.status.in_(("queued", "processing")))
        ).all()
        for row in queued_rows:
            row.status = "cancelled"
            row.completed_at = now
            session.add(row)
        task.status = "cancelled"
        task.updated_at = now
        session.add(task)
        session.commit()
        _emit_dashboard_event(
            session,
            task_id=task.id,
            event_type="dashboard_cancel",
            summary="Dashboard cancelo la tarea.",
            payload={"action": "cancel"},
        )
        return {"ok": True, "action": "cancel", "task_id": task.id}

    if clean_action == "set_priority":
        selected_priority = normalize_priority(priority or "medium")
        row = session.exec(
            select(QueueEntry).where(QueueEntry.task_id == task.id, QueueEntry.status == "queued").order_by(QueueEntry.enqueued_at.desc())
        ).first()
        if not row:
            raise ValueError("queued_entry_not_found")
        row.priority = selected_priority
        row.queue_bucket = derive_queue_bucket(selected_priority)
        session.add(row)
        session.commit()
        _emit_dashboard_event(
            session,
            task_id=task.id,
            event_type="dashboard_set_priority",
            summary=f"Dashboard cambio prioridad a {selected_priority}.",
            payload={"action": "set_priority", "priority": selected_priority},
        )
        return {"ok": True, "action": "set_priority", "task_id": task.id, "priority": selected_priority}

    raise ValueError("unsupported_action")
