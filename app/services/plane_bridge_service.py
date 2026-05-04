from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.domain.swarm.models import SwarmCreate, SwarmRunCreate
from app.domain.swarm.service import create_swarm, run_swarm_cycle
from app.domain.tasks.models import Task
from app.integrations.plane import comment_on_issue, create_issue, list_issues, update_issue


def ensure_plane_bridge_tables(session: Session) -> None:
    conn = session.connection()
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS plane_sync (
                task_id TEXT PRIMARY KEY,
                plane_issue_id TEXT NOT NULL UNIQUE,
                plane_issue_url TEXT,
                sync_status TEXT NOT NULL DEFAULT 'linked',
                last_synced_at DATETIME,
                last_error TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS plane_processed_issues (
                issue_id TEXT PRIMARY KEY,
                issue_url TEXT,
                issue_title TEXT,
                issue_state TEXT,
                labels_json TEXT,
                issue_updated_at TEXT,
                last_swarm_id TEXT,
                last_action TEXT,
                processed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.commit()


def _safe_json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except Exception:
        return None
    return value


def _extract_label_names(issue: dict[str, Any]) -> list[str]:
    labels_value = issue.get("labels")
    if not isinstance(labels_value, list):
        return []
    output: list[str] = []
    for item in labels_value:
        if isinstance(item, str):
            value = item.strip()
        elif isinstance(item, dict):
            value = str(item.get("name") or item.get("label") or "").strip()
        else:
            value = ""
        if value and value not in output:
            output.append(value)
    return output


def _issue_state_name(issue: dict[str, Any]) -> str | None:
    state = issue.get("state")
    if isinstance(state, str):
        value = state.strip()
        return value or None
    if isinstance(state, dict):
        value = str(state.get("name") or "").strip()
        return value or None
    return None


def _issue_updated_at(issue: dict[str, Any]) -> str:
    for key in ("updated_at", "updatedAt", "modified_at", "modifiedAt"):
        value = str(issue.get(key) or "").strip()
        if value:
            return value
    return ""


def _issue_url(issue: dict[str, Any]) -> str | None:
    for key in ("url", "issue_url", "html_url"):
        value = str(issue.get(key) or "").strip()
        if value:
            return value
    issue_id = str(issue.get("id") or "").strip()
    base = settings.plane_issues_base_url.rstrip("/") if settings.plane_issues_base_url else ""
    if issue_id and base:
        return f"{base}/{issue_id}"
    return None


def _extract_issue_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("results", "data", "issues"):
        rows = data.get(key)
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
    return []


def _strip_html(raw: str | None) -> str:
    source = str(raw or "").strip()
    if not source:
        return ""
    text_only = re.sub(r"<[^>]+>", " ", source)
    compact = re.sub(r"\s+", " ", text_only).strip()
    return compact


def _upsert_plane_sync(
    session: Session,
    *,
    task_id: str,
    issue_id: str,
    issue_url: str | None,
    sync_status: str,
    last_error: str | None = None,
) -> None:
    ensure_plane_bridge_tables(session)
    now = datetime.utcnow()
    row = session.connection().execute(
        text("SELECT task_id FROM plane_sync WHERE task_id = :task_id"),
        {"task_id": task_id},
    ).first()
    if row:
        session.connection().execute(
            text(
                """
                UPDATE plane_sync
                SET plane_issue_id = :issue_id,
                    plane_issue_url = :issue_url,
                    sync_status = :sync_status,
                    last_error = :last_error,
                    last_synced_at = :last_synced_at,
                    updated_at = :updated_at
                WHERE task_id = :task_id
                """
            ),
            {
                "task_id": task_id,
                "issue_id": issue_id,
                "issue_url": issue_url,
                "sync_status": sync_status,
                "last_error": last_error,
                "last_synced_at": now,
                "updated_at": now,
            },
        )
    else:
        session.connection().execute(
            text(
                """
                INSERT INTO plane_sync (
                    task_id, plane_issue_id, plane_issue_url, sync_status, last_error, last_synced_at, created_at, updated_at
                ) VALUES (
                    :task_id, :issue_id, :issue_url, :sync_status, :last_error, :last_synced_at, :created_at, :updated_at
                )
                """
            ),
            {
                "task_id": task_id,
                "issue_id": issue_id,
                "issue_url": issue_url,
                "sync_status": sync_status,
                "last_error": last_error,
                "last_synced_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )
    session.commit()


def _get_issue_link_for_task(session: Session, task_id: str) -> dict[str, Any] | None:
    ensure_plane_bridge_tables(session)
    row = session.connection().execute(
        text(
            """
            SELECT task_id, plane_issue_id, plane_issue_url, sync_status, last_synced_at, last_error
            FROM plane_sync
            WHERE task_id = :task_id
            """
        ),
        {"task_id": task_id},
    ).first()
    return dict(row._mapping) if row else None


def _try_mark_issue_state(issue_id: str, *, done: bool) -> bool:
    candidates = (
        [{"state": "Done"}, {"status": "Done"}, {"state": {"name": "Done"}}]
        if done
        else [{"state": "In Progress"}, {"status": "In Progress"}, {"state": {"name": "In Progress"}}]
    )
    for payload in candidates:
        result = update_issue(issue_id, payload)
        if result.ok:
            return True
    return False


def sync_task_status_to_plane(session: Session, *, task: Task, failed_channels: list[str]) -> dict[str, Any]:
    if not settings.plane_sync_enabled:
        return {"ok": False, "reason": "plane_sync_disabled"}
    ensure_plane_bridge_tables(session)
    link = _get_issue_link_for_task(session, task.id)
    has_failure = bool(failed_channels)
    channel_suffix = ",".join(failed_channels) if failed_channels else "none"
    sync_status = "failed" if has_failure else "done"

    if has_failure and not link:
        labels = ["metiche", "managed:metiche", "sync:war-room", "task:failed", f"task:{task.task_type}"]
        description = (
            f"Tarea: {task.id}<br/>"
            f"Tipo: {task.task_type}<br/>"
            f"Estado: failed<br/>"
            f"Canales con falla: {channel_suffix}"
        )
        created = create_issue(
            title=f"[metiche] Tarea fallida: {task.title}",
            description=description,
            labels=labels,
        )
        if not created.ok:
            _upsert_plane_sync(
                session,
                task_id=task.id,
                issue_id=f"error:{task.id}",
                issue_url=None,
                sync_status="error",
                last_error=created.error or "No se pudo crear issue en Plane",
            )
            return {"ok": False, "reason": "create_issue_failed", "error": created.error}

        issue_id = str(created.data.get("id") or "").strip()
        if not issue_id:
            return {"ok": False, "reason": "create_issue_missing_id"}
        issue_url = _issue_url(created.data)
        _upsert_plane_sync(
            session,
            task_id=task.id,
            issue_id=issue_id,
            issue_url=issue_url,
            sync_status=sync_status,
        )
        comment_on_issue(
            issue_id,
            (
                f"Metiche registró falla definitiva en tarea `{task.id}`.<br/>"
                f"Canales fallidos: {channel_suffix}.<br/>"
                "Se etiqueta automáticamente para seguimiento."
            ),
        )
        _try_mark_issue_state(issue_id, done=False)
        return {"ok": True, "action": "issue_created", "issue_id": issue_id, "status": sync_status}

    if not link:
        return {"ok": True, "action": "no_link_no_failure"}

    issue_id = str(link.get("plane_issue_id") or "").strip()
    if not issue_id:
        return {"ok": False, "reason": "link_without_issue_id"}

    if has_failure:
        _try_mark_issue_state(issue_id, done=False)
        comment_on_issue(
            issue_id,
            (
                f"Metiche detectó nueva falla en tarea `{task.id}`.<br/>"
                f"Canales fallidos: {channel_suffix}."
            ),
        )
    else:
        _try_mark_issue_state(issue_id, done=True)
        comment_on_issue(
            issue_id,
            (
                f"Metiche validó tarea `{task.id}` correctamente.<br/>"
                "Se actualiza estado operativo a Done."
            ),
        )

    _upsert_plane_sync(
        session,
        task_id=task.id,
        issue_id=issue_id,
        issue_url=str(link.get("plane_issue_url") or "") or None,
        sync_status=sync_status,
    )
    return {"ok": True, "action": "issue_updated", "issue_id": issue_id, "status": sync_status}


def _processed_issue_row(session: Session, issue_id: str) -> dict[str, Any] | None:
    ensure_plane_bridge_tables(session)
    row = session.connection().execute(
        text(
            """
            SELECT issue_id, issue_updated_at, last_swarm_id, last_action
            FROM plane_processed_issues
            WHERE issue_id = :issue_id
            """
        ),
        {"issue_id": issue_id},
    ).first()
    return dict(row._mapping) if row else None


def _upsert_processed_issue(
    session: Session,
    *,
    issue: dict[str, Any],
    swarm_id: str | None,
    action: str,
) -> None:
    ensure_plane_bridge_tables(session)
    now = datetime.utcnow()
    issue_id = str(issue.get("id") or "").strip()
    issue_url = _issue_url(issue)
    issue_title = str(issue.get("name") or issue.get("title") or "").strip()
    issue_state = _issue_state_name(issue) or ""
    labels_json = json.dumps(_extract_label_names(issue), ensure_ascii=False)
    issue_updated = _issue_updated_at(issue)
    row = _processed_issue_row(session, issue_id)

    if row:
        session.connection().execute(
            text(
                """
                UPDATE plane_processed_issues
                SET issue_url = :issue_url,
                    issue_title = :issue_title,
                    issue_state = :issue_state,
                    labels_json = :labels_json,
                    issue_updated_at = :issue_updated_at,
                    last_swarm_id = :last_swarm_id,
                    last_action = :last_action,
                    processed_at = :processed_at,
                    updated_at = :updated_at
                WHERE issue_id = :issue_id
                """
            ),
            {
                "issue_id": issue_id,
                "issue_url": issue_url,
                "issue_title": issue_title,
                "issue_state": issue_state,
                "labels_json": labels_json,
                "issue_updated_at": issue_updated,
                "last_swarm_id": swarm_id,
                "last_action": action,
                "processed_at": now,
                "updated_at": now,
            },
        )
    else:
        session.connection().execute(
            text(
                """
                INSERT INTO plane_processed_issues (
                    issue_id, issue_url, issue_title, issue_state, labels_json, issue_updated_at,
                    last_swarm_id, last_action, processed_at, created_at, updated_at
                ) VALUES (
                    :issue_id, :issue_url, :issue_title, :issue_state, :labels_json, :issue_updated_at,
                    :last_swarm_id, :last_action, :processed_at, :created_at, :updated_at
                )
                """
            ),
            {
                "issue_id": issue_id,
                "issue_url": issue_url,
                "issue_title": issue_title,
                "issue_state": issue_state,
                "labels_json": labels_json,
                "issue_updated_at": issue_updated,
                "last_swarm_id": swarm_id,
                "last_action": action,
                "processed_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )
    session.commit()


def _should_process_issue(issue: dict[str, Any], processed: dict[str, Any] | None) -> bool:
    updated_at = _issue_updated_at(issue)
    if not processed:
        return True
    last_action = str(processed.get("last_action") or "").strip().lower()
    # Prevent infinite relaunch loops when Metiche itself updates the issue timestamp
    # via comments/state transitions after launching a swarm.
    if last_action == "swarm_launched":
        return False
    previous_updated = str(processed.get("issue_updated_at") or "")
    return bool(updated_at and updated_at != previous_updated)


def process_plane_enjambre_pull(session: Session, *, limit: int = 20) -> dict[str, Any]:
    if not settings.plane_sync_enabled:
        return {"ok": False, "reason": "plane_sync_disabled"}

    ensure_plane_bridge_tables(session)
    pull_label = (settings.plane_sync_pull_label or "run:enjambre").strip() or "run:enjambre"
    pull = list_issues(limit=limit, labels=[pull_label])
    if not pull.ok:
        return {"ok": False, "reason": "list_issues_failed", "error": pull.error}

    issues = _extract_issue_rows(pull.data)
    processed_count = 0
    launched_count = 0
    skipped_count = 0
    errors: list[str] = []

    for issue in issues:
        issue_id = str(issue.get("id") or "").strip()
        if not issue_id:
            continue
        labels = _extract_label_names(issue)
        if pull_label not in labels:
            skipped_count += 1
            continue

        processed_row = _processed_issue_row(session, issue_id)
        if not _should_process_issue(issue, processed_row):
            skipped_count += 1
            continue

        issue_title = str(issue.get("name") or issue.get("title") or f"Issue {issue_id}").strip()
        objective = _strip_html(issue.get("description_html") or issue.get("description")) or issue_title
        if len(objective) < 10:
            objective = f"Resolver issue Plane {issue_id}: {issue_title}"

        try:
            swarm = create_swarm(
                session,
                SwarmCreate(
                    name=f"Plane:{issue_title[:60]}",
                    goal=objective,
                    policy="narrative-consensus",
                    agents=["whatsapp", "telegram", "deepseek", "plane"],
                    parent_issue_id=issue_id,
                ),
            )
            run = run_swarm_cycle(
                session,
                swarm.id,
                SwarmRunCreate(
                    objective=objective,
                    related_task_id=None,
                    client_key=f"plane:{issue_id}",
                    max_cycles=1,
                ),
            )
            launched_count += 1
            processed_count += 1
            comment_on_issue(
                issue_id,
                (
                    f"Metiche lanzó enjambre `{swarm.id}` desde etiqueta `{pull_label}`.<br/>"
                    f"Decisión: {run.decision if run else 'unknown'}."
                ),
            )
            _try_mark_issue_state(issue_id, done=bool(run and run.decision == "accept"))
            _upsert_processed_issue(
                session,
                issue=issue,
                swarm_id=swarm.id,
                action="swarm_launched",
            )
        except Exception as exc:  # pragma: no cover - defensivo
            errors.append(f"{issue_id}:{exc}")
            processed_count += 1
            _upsert_processed_issue(
                session,
                issue=issue,
                swarm_id=None,
                action="error",
            )

    return {
        "ok": True,
        "scanned": len(issues),
        "processed": processed_count,
        "launched": launched_count,
        "skipped": skipped_count,
        "errors": errors,
    }


def list_plane_related_issues(session: Session, *, limit: int = 30) -> list[dict[str, Any]]:
    ensure_plane_bridge_tables(session)
    safe_limit = max(1, min(limit, 200))
    rows = session.connection().execute(
        text(
            """
            SELECT
                ps.task_id AS task_id,
                t.title AS task_title,
                ps.plane_issue_id AS issue_id,
                ps.plane_issue_url AS issue_url,
                ps.sync_status AS sync_status,
                ps.last_synced_at AS last_synced_at,
                ps.last_error AS last_error,
                NULL AS issue_state,
                NULL AS labels_json,
                NULL AS last_swarm_id,
                NULL AS last_action,
                NULL AS processed_at
            FROM plane_sync ps
            LEFT JOIN task t ON t.id = ps.task_id
            UNION ALL
            SELECT
                NULL AS task_id,
                NULL AS task_title,
                ppi.issue_id AS issue_id,
                ppi.issue_url AS issue_url,
                ppi.last_action AS sync_status,
                ppi.updated_at AS last_synced_at,
                NULL AS last_error,
                ppi.issue_state AS issue_state,
                ppi.labels_json AS labels_json,
                ppi.last_swarm_id AS last_swarm_id,
                ppi.last_action AS last_action,
                ppi.processed_at AS processed_at
            FROM plane_processed_issues ppi
            ORDER BY last_synced_at DESC
            LIMIT :limit
            """
        ),
        {"limit": safe_limit},
    ).fetchall()

    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        item = dict(row._mapping)
        issue_id = str(item.get("issue_id") or "").strip()
        if not issue_id or issue_id in seen:
            continue
        seen.add(issue_id)
        labels_value = _safe_json_loads(item.get("labels_json"))
        labels = [str(v) for v in labels_value] if isinstance(labels_value, list) else []
        output.append(
            {
                "issue_id": issue_id,
                "issue_url": item.get("issue_url"),
                "task_id": item.get("task_id"),
                "task_title": item.get("task_title"),
                "sync_status": item.get("sync_status"),
                "issue_state": item.get("issue_state"),
                "labels": labels,
                "last_swarm_id": item.get("last_swarm_id"),
                "last_action": item.get("last_action"),
                "last_error": item.get("last_error"),
                "last_synced_at": item.get("last_synced_at"),
                "processed_at": item.get("processed_at"),
            }
        )
    return output
