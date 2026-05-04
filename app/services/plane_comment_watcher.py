from __future__ import annotations

import json
import re
import shlex
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Any
from uuid import uuid4

try:
    import psycopg2
except Exception:  # pragma: no cover - optional dependency at runtime
    psycopg2 = None

from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.domain.swarm.models import SwarmCreate, SwarmRunCreate
from app.domain.swarm.service import create_swarm, run_swarm_cycle
from app.integrations.plane import comment_on_issue, get_issue
from app.services.dashboard_service import get_dashboard_stats, perform_task_action
from app.services.plane_bridge_service import process_plane_enjambre_pull
from app.services.traje_iron_man.operaciones import get_traje_status, run_traje_operation

PENDING_COMMAND_LABEL = "pending-command"
LAST_ACTION_OK_LABEL = "last-action:ok"
LAST_ACTION_ERROR_LABEL = "last-action:error"


def ensure_plane_comment_tables(session: Session) -> None:
    session.connection().execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS plane_processed_comments (
                comment_id TEXT PRIMARY KEY,
                issue_id TEXT NOT NULL,
                author_email TEXT,
                command_text TEXT NOT NULL,
                action_name TEXT NOT NULL,
                params_json TEXT,
                status TEXT NOT NULL DEFAULT 'processing',
                result_json TEXT,
                error_text TEXT,
                started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at DATETIME
            )
            """
        )
    )
    session.commit()


def list_plane_command_history(session: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    ensure_plane_comment_tables(session)
    safe_limit = max(1, min(limit, 200))
    rows = session.connection().execute(
        text(
            """
            SELECT
                comment_id, issue_id, author_email, command_text, action_name,
                params_json, status, result_json, error_text, started_at, finished_at
            FROM plane_processed_comments
            ORDER BY started_at DESC
            LIMIT :limit
            """
        ),
        {"limit": safe_limit},
    ).fetchall()
    output: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row._mapping)
        params_value = _safe_json_loads(payload.get("params_json"))
        result_value = _safe_json_loads(payload.get("result_json"))
        output.append(
            {
                "comment_id": payload.get("comment_id"),
                "issue_id": payload.get("issue_id"),
                "author_email": payload.get("author_email"),
                "command_text": payload.get("command_text"),
                "action_name": payload.get("action_name"),
                "params": params_value if isinstance(params_value, dict) else {},
                "status": payload.get("status"),
                "result": result_value,
                "error_text": payload.get("error_text"),
                "started_at": payload.get("started_at"),
                "finished_at": payload.get("finished_at"),
            }
        )
    return output


def process_plane_comment_commands(*, limit: int = 20) -> dict[str, Any]:
    if not settings.plane_sync_enabled:
        return {"ok": False, "reason": "plane_sync_disabled"}
    candidates = _fetch_plane_comments(limit=max(1, min(limit, 100)))
    if not candidates:
        return {"ok": True, "scanned": 0, "processed": 0, "skipped": 0, "errors": []}

    allowlist = _author_allowlist()
    processed = 0
    skipped = 0
    errors: list[str] = []

    for item in candidates:
        author = str(item.get("author_email") or "").strip().lower()
        if allowlist and author not in allowlist:
            skipped += 1
            continue

        parsed = _parse_command(item.get("command_text"))
        if not parsed:
            skipped += 1
            continue
        action_name, params = parsed

        with Session(engine) as session:
            ensure_plane_comment_tables(session)
            if not _claim_comment(
                session,
                comment_id=item["comment_id"],
                issue_id=item["issue_id"],
                author_email=author,
                command_text=str(item.get("command_text") or ""),
                action_name=action_name,
                params=params,
            ):
                skipped += 1
                continue

        issue_id = item["issue_id"]
        _add_issue_label(issue_id, PENDING_COMMAND_LABEL)
        comment_on_issue(issue_id, f"ACK comando `{action_name}`: procesando...")

        status = "done"
        result_payload: dict[str, Any] | None = None
        error_text: str | None = None
        try:
            result_payload = _run_action_with_timeout(issue_id=issue_id, action_name=action_name, params=params)
            comment_on_issue(issue_id, f"✅ DONE `{action_name}`\n\n```json\n{json.dumps(result_payload, ensure_ascii=False)}\n```")
            _set_issue_last_action_labels(issue_id, ok=True)
        except Exception as exc:  # pragma: no cover - defensive
            status = "error"
            error_text = str(exc)
            comment_on_issue(issue_id, f"❌ ERROR `{action_name}`: {error_text}")
            _set_issue_last_action_labels(issue_id, ok=False)
            errors.append(f"{item['comment_id']}:{error_text}")
        finally:
            _remove_issue_label(issue_id, PENDING_COMMAND_LABEL)

        with Session(engine) as session:
            _finish_comment(
                session,
                comment_id=item["comment_id"],
                status=status,
                result_payload=result_payload,
                error_text=error_text,
            )
        processed += 1

    return {
        "ok": True,
        "scanned": len(candidates),
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
    }


def _safe_json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _author_allowlist() -> set[str]:
    raw = str(settings.plane_command_author_allowlist or "").strip()
    if not raw:
        return set()
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _extract_command_text(source: str | None) -> str:
    value = str(source or "").strip()
    if not value:
        return ""
    compact = re.sub(r"\s+", " ", value).strip()
    return compact


def _parse_command(raw: str | None) -> tuple[str, dict[str, str]] | None:
    text_value = _extract_command_text(raw)
    if not text_value:
        return None
    try:
        parts = shlex.split(text_value)
    except Exception:
        parts = text_value.split()
    if not parts or parts[0].lower() != "/metiche":
        return None
    action_name = ""
    params: dict[str, str] = {}
    for token in parts[1:]:
        lower = token.lower()
        if lower.startswith("accion:"):
            action_name = token.split(":", 1)[1].strip().lower()
            continue
        if lower.startswith("accion="):
            action_name = token.split("=", 1)[1].strip().lower()
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            clean_key = key.strip().lower()
            if clean_key:
                params[clean_key] = value.strip()
    if not action_name:
        return None
    return action_name, params


def _plane_pg_connect():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 no disponible")
    kwargs = dict(
        host=settings.plane_pg_host or "localhost",
        port=settings.plane_pg_port or 5432,
        user=settings.plane_pg_user,
        password=settings.plane_pg_password,
        dbname=settings.plane_pg_dbname,
        connect_timeout=max(1, int(settings.plane_timeout_seconds)),
    )
    try:
        return psycopg2.connect(**kwargs)
    except Exception:
        if kwargs["host"] in {"localhost", "127.0.0.1"}:
            kwargs["host"] = "plane-db"
            return psycopg2.connect(**kwargs)
        raise


def _fetch_plane_comments(*, limit: int) -> list[dict[str, str]]:
    if not settings.plane_use_direct_db:
        return []
    with _plane_pg_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                c.id::text AS comment_id,
                c.issue_id::text AS issue_id,
                COALESCE(u.email, '') AS author_email,
                COALESCE(c.comment_stripped, '') AS command_text
            FROM issue_comments c
            LEFT JOIN users u ON u.id = c.created_by_id
            WHERE c.deleted_at IS NULL
            ORDER BY c.created_at DESC
            LIMIT %s
            """,
            (max(1, min(limit, 100)),),
        )
        rows = cur.fetchall() or []
    output: list[dict[str, str]] = []
    for row in rows:
        output.append(
            {
                "comment_id": str(row[0] or ""),
                "issue_id": str(row[1] or ""),
                "author_email": str(row[2] or "").strip().lower(),
                "command_text": str(row[3] or ""),
            }
        )
    return output


def _claim_comment(
    session: Session,
    *,
    comment_id: str,
    issue_id: str,
    author_email: str,
    command_text: str,
    action_name: str,
    params: dict[str, str],
) -> bool:
    row = session.connection().execute(
        text("SELECT comment_id FROM plane_processed_comments WHERE comment_id = :comment_id"),
        {"comment_id": comment_id},
    ).first()
    if row:
        return False
    session.connection().execute(
        text(
            """
            INSERT INTO plane_processed_comments (
                comment_id, issue_id, author_email, command_text, action_name, params_json, status, started_at
            ) VALUES (
                :comment_id, :issue_id, :author_email, :command_text, :action_name, :params_json, :status, :started_at
            )
            """
        ),
        {
            "comment_id": comment_id,
            "issue_id": issue_id,
            "author_email": author_email,
            "command_text": command_text,
            "action_name": action_name,
            "params_json": json.dumps(params, ensure_ascii=False),
            "status": "processing",
            "started_at": datetime.utcnow(),
        },
    )
    session.commit()
    return True


def _finish_comment(
    session: Session,
    *,
    comment_id: str,
    status: str,
    result_payload: dict[str, Any] | None,
    error_text: str | None,
) -> None:
    session.connection().execute(
        text(
            """
            UPDATE plane_processed_comments
            SET status = :status,
                result_json = :result_json,
                error_text = :error_text,
                finished_at = :finished_at
            WHERE comment_id = :comment_id
            """
        ),
        {
            "comment_id": comment_id,
            "status": status,
            "result_json": json.dumps(result_payload, ensure_ascii=False) if result_payload is not None else None,
            "error_text": error_text,
            "finished_at": datetime.utcnow(),
        },
    )
    session.commit()


def _run_action_with_timeout(*, issue_id: str, action_name: str, params: dict[str, str]) -> dict[str, Any]:
    timeout_seconds = max(5, int(settings.plane_command_timeout_seconds))
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_execute_action, issue_id, action_name, params)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            raise RuntimeError(f"timeout_exceeded:{timeout_seconds}s") from exc


def _execute_action(issue_id: str, action_name: str, params: dict[str, str]) -> dict[str, Any]:
    if action_name == "enjambre.run":
        issue = get_issue(issue_id)
        title = f"Plane issue {issue_id}"
        objective = f"Resolver issue {issue_id}"
        if issue.ok and isinstance(issue.data, dict):
            title = str(issue.data.get("name") or title)
            html = str(issue.data.get("description_html") or "")
            cleaned = re.sub(r"<[^>]+>", " ", html)
            objective = re.sub(r"\s+", " ", cleaned).strip() or objective
        with Session(engine) as session:
            swarm = create_swarm(
                session,
                SwarmCreate(
                    name=f"Plane:{title[:60]}",
                    goal=objective,
                    policy="narrative-consensus",
                    agents=["whatsapp", "telegram", "deepseek", "plane"],
                    parent_issue_id=params.get("parent_issue_id") or issue_id,
                ),
            )
            run = run_swarm_cycle(
                session,
                swarm.id,
                SwarmRunCreate(
                    objective=objective,
                    related_task_id=params.get("task_id"),
                    client_key=f"plane:{issue_id}",
                    max_cycles=max(1, int(params.get("max_cycles", "1"))),
                ),
            )
        return {"ok": True, "action": action_name, "swarm_id": swarm.id, "decision": run.decision if run else None}

    if action_name == "task.retry":
        task_id = str(params.get("task_id") or "").strip()
        if not task_id:
            raise RuntimeError("missing_task_id")
        with Session(engine) as session:
            result = perform_task_action(
                session,
                task_id=task_id,
                action="retry",
                priority=str(params.get("priority") or "high"),
            )
        return {"ok": True, "action": action_name, "result": result}

    if action_name == "task.cancel":
        task_id = str(params.get("task_id") or "").strip()
        if not task_id:
            raise RuntimeError("missing_task_id")
        with Session(engine) as session:
            result = perform_task_action(session, task_id=task_id, action="cancel")
        return {"ok": True, "action": action_name, "result": result}

    if action_name == "traje.archivar":
        lote = max(1, min(int(params.get("lote", "30")), 200))
        dry_run = str(params.get("dryrun", "true")).strip().lower() in {"1", "true", "yes", "si"}
        result = run_traje_operation(operacion="archivar", lote=lote, dry_run=dry_run, trigger="plane_comment")
        return {"ok": True, "action": action_name, "result": result}

    if action_name == "traje.limpiar-low":
        lote = max(1, min(int(params.get("lote", "20")), 200))
        dry_run = str(params.get("dryrun", "false")).strip().lower() in {"1", "true", "yes", "si"}
        result = run_traje_operation(operacion="limpiar-low", lote=lote, dry_run=dry_run, trigger="plane_comment")
        return {"ok": True, "action": action_name, "result": result}

    if action_name == "traje.status":
        return {"ok": True, "action": action_name, "result": get_traje_status()}

    if action_name == "sync.pull":
        with Session(engine) as session:
            result = process_plane_enjambre_pull(session, limit=max(1, min(int(params.get("limit", "20")), 200)))
        return {"ok": True, "action": action_name, "result": result}

    if action_name == "info.health":
        with Session(engine) as session:
            stats = get_dashboard_stats(session)
        return {
            "ok": True,
            "action": action_name,
            "result": {
                "system_health": stats.get("system_health"),
                "failures_last_10m": stats.get("failures_last_10m"),
                "active_critical_alerts": stats.get("active_critical_alerts"),
                "generated_at": str(stats.get("generated_at") or ""),
            },
        }

    raise RuntimeError(f"unsupported_action:{action_name}")


def _add_issue_label(issue_id: str, label_name: str) -> None:
    if not settings.plane_use_direct_db:
        return
    with _plane_pg_connect() as conn:
        cur = conn.cursor()
        issue_info = _issue_scope(cur, issue_id)
        if not issue_info:
            return
        project_id, workspace_id = issue_info
        label_id = _ensure_label(cur, label_name=label_name, project_id=project_id, workspace_id=workspace_id)
        cur.execute(
            """
            SELECT id::text
            FROM issue_labels
            WHERE issue_id = %s::uuid
              AND label_id = %s::uuid
              AND deleted_at IS NULL
            LIMIT 1
            """,
            (issue_id, label_id),
        )
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO issue_labels (
                    created_at, updated_at, id, issue_id, label_id, project_id, workspace_id
                ) VALUES (
                    now(), now(), %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s::uuid
                )
                """,
                (str(uuid4()), issue_id, label_id, project_id, workspace_id),
            )
        conn.commit()


def _remove_issue_label(issue_id: str, label_name: str) -> None:
    if not settings.plane_use_direct_db:
        return
    with _plane_pg_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE issue_labels il
            SET deleted_at = now(), updated_at = now()
            WHERE il.issue_id = %s::uuid
              AND il.deleted_at IS NULL
              AND il.label_id IN (
                  SELECT l.id
                  FROM labels l
                  WHERE lower(l.name) = %s
                    AND l.deleted_at IS NULL
              )
            """,
            (issue_id, label_name.lower()),
        )
        conn.commit()


def _set_issue_last_action_labels(issue_id: str, *, ok: bool) -> None:
    _remove_labels_by_prefix(issue_id, "last-action:")
    _add_issue_label(issue_id, LAST_ACTION_OK_LABEL if ok else LAST_ACTION_ERROR_LABEL)


def _remove_labels_by_prefix(issue_id: str, prefix: str) -> None:
    if not settings.plane_use_direct_db:
        return
    with _plane_pg_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE issue_labels il
            SET deleted_at = now(), updated_at = now()
            WHERE il.issue_id = %s::uuid
              AND il.deleted_at IS NULL
              AND il.label_id IN (
                  SELECT l.id
                  FROM labels l
                  WHERE lower(l.name) LIKE %s
                    AND l.deleted_at IS NULL
              )
            """,
            (issue_id, f"{prefix.lower()}%"),
        )
        conn.commit()


def _issue_scope(cur, issue_id: str) -> tuple[str, str] | None:
    cur.execute(
        """
        SELECT project_id::text, workspace_id::text
        FROM issues
        WHERE id = %s::uuid AND deleted_at IS NULL
        LIMIT 1
        """,
        (issue_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return str(row[0]), str(row[1])


def _ensure_label(cur, *, label_name: str, project_id: str, workspace_id: str) -> str:
    cur.execute(
        """
        SELECT id::text
        FROM labels
        WHERE workspace_id = %s::uuid
          AND project_id = %s::uuid
          AND deleted_at IS NULL
          AND lower(name) = %s
        LIMIT 1
        """,
        (workspace_id, project_id, label_name.lower()),
    )
    row = cur.fetchone()
    if row:
        return str(row[0])
    label_id = str(uuid4())
    cur.execute(
        """
        INSERT INTO labels (
            created_at, updated_at, id, name, description, project_id, workspace_id, color, sort_order
        ) VALUES (
            now(), now(), %s::uuid, %s, '', %s::uuid, %s::uuid, '#22C55E', 0
        )
        """,
        (label_id, label_name, project_id, workspace_id),
    )
    return label_id
