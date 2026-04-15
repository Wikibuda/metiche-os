from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib import error, request
from uuid import uuid4

try:
    import psycopg2
    from psycopg2.extras import Json
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None
    Json = None

from app.core.config import settings


@dataclass
class PlaneResponse:
    ok: bool
    status_code: int
    data: dict[str, Any] | list[dict[str, Any]]
    error: str | None = None


def _direct_db_enabled() -> bool:
    return bool(settings.plane_use_direct_db)


def _strip_html(raw: str) -> str:
    text_only = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", text_only).strip()


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = settings.plane_api_key or settings.plane_api_token
    bearer = settings.plane_bearer_token or settings.plane_api_token
    if api_key:
        headers["x-api-key"] = api_key
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return headers


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> PlaneResponse:
    body = json.dumps(payload or {}).encode("utf-8")
    req = request.Request(url=url, data=body, headers=_headers(), method=method)
    try:
        with request.urlopen(req, timeout=settings.plane_timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
            return PlaneResponse(ok=True, status_code=resp.getcode(), data=json.loads(raw) if raw else {})
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        return PlaneResponse(ok=False, status_code=exc.code, data={}, error=raw or str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        return PlaneResponse(ok=False, status_code=0, data={}, error=str(exc))


def _request_get(url: str) -> PlaneResponse:
    req = request.Request(url=url, headers=_headers(), method="GET")
    try:
        with request.urlopen(req, timeout=settings.plane_timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
            return PlaneResponse(ok=True, status_code=resp.getcode(), data=json.loads(raw) if raw else {})
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        return PlaneResponse(ok=False, status_code=exc.code, data={}, error=raw or str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        return PlaneResponse(ok=False, status_code=0, data={}, error=str(exc))


def _direct_db_not_available_error() -> PlaneResponse:
    if settings.plane_db_type.lower() != "postgres":
        return PlaneResponse(
            ok=False,
            status_code=0,
            data={},
            error=f"PLANE_DB_TYPE no soportado: {settings.plane_db_type}",
        )
    if psycopg2 is None:
        return PlaneResponse(
            ok=False,
            status_code=0,
            data={},
            error="psycopg2 no instalado para modo PLANE_USE_DIRECT_DB=true",
        )
    return PlaneResponse(ok=True, status_code=200, data={})


def _pg_connect():
    assert psycopg2 is not None
    host = settings.plane_pg_host or "localhost"
    kwargs = dict(
        host=host,
        port=settings.plane_pg_port or 5432,
        user=settings.plane_pg_user,
        password=settings.plane_pg_password,
        dbname=settings.plane_pg_dbname,
        connect_timeout=max(1, int(settings.plane_timeout_seconds)),
    )
    try:
        return psycopg2.connect(**kwargs)
    except Exception:
        # Common fallbacks for dockerized deployments.
        fallback_hosts: list[str] = []
        if host in {"localhost", "127.0.0.1"}:
            fallback_hosts.extend(["plane-db", "host.docker.internal"])
        elif host != "host.docker.internal":
            fallback_hosts.append("host.docker.internal")
        for fallback in fallback_hosts:
            try:
                kwargs["host"] = fallback
                return psycopg2.connect(**kwargs)
            except Exception:
                continue
        raise


def _issue_url_from_id(issue_id: str) -> str | None:
    if settings.plane_issues_base_url:
        return f"{settings.plane_issues_base_url.rstrip('/')}/{issue_id}"
    return None


def _resolve_project_workspace(conn) -> tuple[str, str]:
    cur = conn.cursor()
    if settings.plane_project_id:
        cur.execute(
            """
            SELECT id::text, workspace_id::text
            FROM projects
            WHERE id = %s::uuid AND deleted_at IS NULL
            LIMIT 1
            """,
            (settings.plane_project_id,),
        )
        row = cur.fetchone()
        if row:
            return str(row[0]), str(row[1])
    cur.execute(
        """
        SELECT id::text, workspace_id::text
        FROM projects
        WHERE deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("No hay proyectos en Plane")
    return str(row[0]), str(row[1])


def _resolve_state_id(conn, project_id: str, state_name: str | None) -> str | None:
    cur = conn.cursor()
    wanted = (state_name or "").strip().lower()
    if wanted:
        cur.execute(
            """
            SELECT id::text
            FROM states
            WHERE project_id = %s::uuid
              AND deleted_at IS NULL
              AND lower(name) = %s
            ORDER BY "default" DESC, sequence ASC
            LIMIT 1
            """,
            (project_id, wanted),
        )
        row = cur.fetchone()
        if row:
            return str(row[0])

    target_group = "unstarted"
    if any(token in wanted for token in ("done", "completed", "closed")):
        target_group = "completed"
    elif any(token in wanted for token in ("progress", "started", "doing")):
        target_group = "started"

    cur.execute(
        """
        SELECT id::text
        FROM states
        WHERE project_id = %s::uuid
          AND deleted_at IS NULL
          AND "group" = %s
        ORDER BY "default" DESC, sequence ASC
        LIMIT 1
        """,
        (project_id, target_group),
    )
    row = cur.fetchone()
    return str(row[0]) if row else None


def _ensure_label(conn, *, label_name: str, project_id: str, workspace_id: str) -> str:
    cur = conn.cursor()
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
    found = cur.fetchone()
    if found:
        return str(found[0])

    label_id = str(uuid4())
    cur.execute(
        """
        INSERT INTO labels (
            created_at, updated_at, id, name, description, project_id, workspace_id, color, sort_order
        ) VALUES (
            now(), now(), %s::uuid, %s, '', %s::uuid, %s::uuid, '#4F46E5', 0
        )
        """,
        (label_id, label_name.strip(), project_id, workspace_id),
    )
    return label_id


def _load_issue_direct(conn, issue_id: str) -> dict[str, Any] | None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT i.id::text, i.name, i.description_html, i.updated_at::text, COALESCE(s.name, '') AS state_name
        FROM issues i
        LEFT JOIN states s ON s.id = i.state_id
        WHERE i.id = %s::uuid AND i.deleted_at IS NULL
        LIMIT 1
        """,
        (issue_id,),
    )
    row = cur.fetchone()
    if not row:
        return None

    cur.execute(
        """
        SELECT l.name
        FROM issue_labels il
        JOIN labels l ON l.id = il.label_id
        WHERE il.issue_id = %s::uuid
          AND il.deleted_at IS NULL
          AND l.deleted_at IS NULL
        ORDER BY l.name
        """,
        (issue_id,),
    )
    labels = [{"name": str(item[0])} for item in cur.fetchall()]
    return {
        "id": str(row[0]),
        "name": str(row[1] or ""),
        "description_html": str(row[2] or ""),
        "updated_at": str(row[3] or ""),
        "state": {"name": str(row[4] or "")},
        "labels": labels,
        "url": _issue_url_from_id(str(row[0])),
    }


def _create_issue_direct(title: str, description: str, labels: list[str] | None = None) -> PlaneResponse:
    check = _direct_db_not_available_error()
    if not check.ok:
        return check
    try:
        with _pg_connect() as conn:
            conn.autocommit = False
            project_id, workspace_id = _resolve_project_workspace(conn)
            state_id = _resolve_state_id(conn, project_id, "todo")
            cur = conn.cursor()
            cur.execute(
                "SELECT COALESCE(MAX(sequence_id), 0) + 1 FROM issues WHERE project_id = %s::uuid",
                (project_id,),
            )
            next_seq = int(cur.fetchone()[0] or 1)
            issue_id = str(uuid4())
            cur.execute(
                """
                INSERT INTO issues (
                    created_at, updated_at, id, name, description, priority, sequence_id,
                    project_id, state_id, workspace_id, description_html, sort_order, is_draft
                ) VALUES (
                    now(), now(), %s::uuid, %s, %s::jsonb, 'medium', %s,
                    %s::uuid, %s::uuid, %s::uuid, %s, %s, false
                )
                """,
                (
                    issue_id,
                    title.strip(),
                    Json({}) if Json else "{}",
                    next_seq,
                    project_id,
                    state_id,
                    workspace_id,
                    description or "",
                    float(next_seq),
                ),
            )

            for label in labels or []:
                cleaned = label.strip()
                if not cleaned:
                    continue
                label_id = _ensure_label(conn, label_name=cleaned, project_id=project_id, workspace_id=workspace_id)
                cur.execute(
                    """
                    INSERT INTO issue_labels (
                        created_at, updated_at, id, issue_id, label_id, project_id, workspace_id
                    ) VALUES (
                        now(), now(), %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s::uuid
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    (str(uuid4()), issue_id, label_id, project_id, workspace_id),
                )

            conn.commit()
            loaded = _load_issue_direct(conn, issue_id)
            return PlaneResponse(ok=True, status_code=201, data=loaded or {"id": issue_id})
    except Exception as exc:
        return PlaneResponse(ok=False, status_code=0, data={}, error=str(exc))


def _update_issue_direct(issue_id: str, fields: dict[str, Any]) -> PlaneResponse:
    check = _direct_db_not_available_error()
    if not check.ok:
        return check
    try:
        with _pg_connect() as conn:
            conn.autocommit = False
            cur = conn.cursor()
            cur.execute(
                "SELECT project_id::text FROM issues WHERE id = %s::uuid AND deleted_at IS NULL LIMIT 1",
                (issue_id,),
            )
            row = cur.fetchone()
            if not row:
                return PlaneResponse(ok=False, status_code=404, data={}, error="Issue no encontrado")
            project_id = str(row[0])

            desired_state: str | None = None
            state_value = fields.get("state")
            status_value = fields.get("status")
            if isinstance(state_value, str):
                desired_state = state_value
            elif isinstance(state_value, dict):
                desired_state = str(state_value.get("name") or "").strip() or None
            elif isinstance(status_value, str):
                desired_state = status_value

            if desired_state:
                state_id = _resolve_state_id(conn, project_id, desired_state)
                if state_id:
                    done = any(token in desired_state.lower() for token in ("done", "completed", "closed"))
                    cur.execute(
                        """
                        UPDATE issues
                        SET state_id = %s::uuid,
                            completed_at = CASE WHEN %s THEN now() ELSE NULL END,
                            updated_at = now()
                        WHERE id = %s::uuid
                        """,
                        (state_id, done, issue_id),
                    )
                else:
                    cur.execute("UPDATE issues SET updated_at = now() WHERE id = %s::uuid", (issue_id,))
            else:
                cur.execute("UPDATE issues SET updated_at = now() WHERE id = %s::uuid", (issue_id,))

            conn.commit()
            loaded = _load_issue_direct(conn, issue_id)
            return PlaneResponse(ok=bool(loaded), status_code=200 if loaded else 404, data=loaded or {})
    except Exception as exc:
        return PlaneResponse(ok=False, status_code=0, data={}, error=str(exc))


def _comment_issue_direct(issue_id: str, comment: str) -> PlaneResponse:
    check = _direct_db_not_available_error()
    if not check.ok:
        return check
    try:
        with _pg_connect() as conn:
            conn.autocommit = False
            cur = conn.cursor()
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
                return PlaneResponse(ok=False, status_code=404, data={}, error="Issue no encontrado")

            project_id, workspace_id = str(row[0]), str(row[1])
            comment_id = str(uuid4())
            html = str(comment or "")
            stripped = _strip_html(html)
            cur.execute(
                """
                INSERT INTO issue_comments (
                    created_at, updated_at, id, comment_stripped, attachments,
                    issue_id, project_id, workspace_id, comment_html, comment_json, access
                ) VALUES (
                    now(), now(), %s::uuid, %s, ARRAY[]::varchar[],
                    %s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, 'INTERNAL'
                )
                """,
                (comment_id, stripped, issue_id, project_id, workspace_id, html, Json({}) if Json else "{}"),
            )
            conn.commit()
            return PlaneResponse(ok=True, status_code=201, data={"id": comment_id})
    except Exception as exc:
        return PlaneResponse(ok=False, status_code=0, data={}, error=str(exc))


def _get_issue_direct(issue_id: str) -> PlaneResponse:
    check = _direct_db_not_available_error()
    if not check.ok:
        return check
    try:
        with _pg_connect() as conn:
            loaded = _load_issue_direct(conn, issue_id)
            if not loaded:
                return PlaneResponse(ok=False, status_code=404, data={}, error="Issue no encontrado")
            return PlaneResponse(ok=True, status_code=200, data=loaded)
    except Exception as exc:
        return PlaneResponse(ok=False, status_code=0, data={}, error=str(exc))


def _list_issues_direct(*, limit: int = 50, labels: list[str] | None = None) -> PlaneResponse:
    check = _direct_db_not_available_error()
    if not check.ok:
        return check
    safe_limit = max(1, min(limit, 200))
    wanted = {item.strip().lower() for item in (labels or []) if item.strip()}
    try:
        with _pg_connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT i.id::text, i.name, i.description_html, i.updated_at::text, COALESCE(s.name, '') AS state_name
                FROM issues i
                LEFT JOIN states s ON s.id = i.state_id
                WHERE i.deleted_at IS NULL
                ORDER BY i.updated_at DESC
                LIMIT %s
                """,
                (safe_limit * 5 if wanted else safe_limit,),
            )
            rows = cur.fetchall()
            output: list[dict[str, Any]] = []
            for row in rows:
                issue_id = str(row[0])
                cur.execute(
                    """
                    SELECT l.name
                    FROM issue_labels il
                    JOIN labels l ON l.id = il.label_id
                    WHERE il.issue_id = %s::uuid
                      AND il.deleted_at IS NULL
                      AND l.deleted_at IS NULL
                    ORDER BY l.name
                    """,
                    (issue_id,),
                )
                label_names = [str(item[0]) for item in cur.fetchall()]
                label_set = {name.lower() for name in label_names}
                if wanted and not (wanted & label_set):
                    continue
                output.append(
                    {
                        "id": issue_id,
                        "name": str(row[1] or ""),
                        "description_html": str(row[2] or ""),
                        "updated_at": str(row[3] or ""),
                        "state": {"name": str(row[4] or "")},
                        "labels": [{"name": name} for name in label_names],
                        "url": _issue_url_from_id(issue_id),
                    }
                )
                if len(output) >= safe_limit:
                    break
            return PlaneResponse(ok=True, status_code=200, data={"results": output})
    except Exception as exc:
        return PlaneResponse(ok=False, status_code=0, data={}, error=str(exc))


def _issues_base_url() -> str | None:
    if settings.plane_issues_base_url:
        return settings.plane_issues_base_url.rstrip("/")
    base_url = settings.plane_base_url or settings.plane_api_url
    if base_url and settings.plane_workspace_slug and settings.plane_project_id:
        return (
            f"{base_url.rstrip('/')}/api/v1/workspaces/"
            f"{settings.plane_workspace_slug}/projects/{settings.plane_project_id}/issues"
        )
    return None


def create_issue(title: str, description: str, labels: list[str] | None = None) -> PlaneResponse:
    if _direct_db_enabled():
        return _create_issue_direct(title, description, labels)
    base = _issues_base_url()
    if not settings.plane_sync_enabled:
        return PlaneResponse(ok=False, status_code=0, data={}, error="plane_sync_enabled=false")
    if not base:
        return PlaneResponse(ok=False, status_code=0, data={}, error="Plane base URL no configurada")
    payload: dict[str, Any] = {"name": title, "description_html": description}
    if labels:
        payload["labels"] = labels
    return _request_json("POST", base, payload)


def update_issue(issue_id: str, fields: dict[str, Any]) -> PlaneResponse:
    if _direct_db_enabled():
        return _update_issue_direct(issue_id, fields)
    base = _issues_base_url()
    if not settings.plane_sync_enabled:
        return PlaneResponse(ok=False, status_code=0, data={}, error="plane_sync_enabled=false")
    if not base:
        return PlaneResponse(ok=False, status_code=0, data={}, error="Plane base URL no configurada")
    return _request_json("PATCH", f"{base}/{issue_id}", fields)


def comment_on_issue(issue_id: str, comment: str) -> PlaneResponse:
    if _direct_db_enabled():
        return _comment_issue_direct(issue_id, comment)
    base = _issues_base_url()
    if not settings.plane_sync_enabled:
        return PlaneResponse(ok=False, status_code=0, data={}, error="plane_sync_enabled=false")
    if not base:
        return PlaneResponse(ok=False, status_code=0, data={}, error="Plane base URL no configurada")
    comments_url = f"{base}/{issue_id}/comments"
    return _request_json("POST", comments_url, {"comment_html": comment})


def get_issue(issue_id: str) -> PlaneResponse:
    if _direct_db_enabled():
        return _get_issue_direct(issue_id)
    base = _issues_base_url()
    if not settings.plane_sync_enabled:
        return PlaneResponse(ok=False, status_code=0, data={}, error="plane_sync_enabled=false")
    if not base:
        return PlaneResponse(ok=False, status_code=0, data={}, error="Plane base URL no configurada")
    return _request_get(f"{base}/{issue_id}")


def list_issues(*, limit: int = 50, labels: list[str] | None = None) -> PlaneResponse:
    if _direct_db_enabled():
        return _list_issues_direct(limit=limit, labels=labels)
    base = _issues_base_url()
    if not settings.plane_sync_enabled:
        return PlaneResponse(ok=False, status_code=0, data={}, error="plane_sync_enabled=false")
    if not base:
        return PlaneResponse(ok=False, status_code=0, data={}, error="Plane base URL no configurada")
    params: dict[str, Any] = {"limit": max(1, min(limit, 200))}
    if labels:
        params["labels"] = ",".join([item for item in labels if item.strip()])
    url = f"{base}?{urlencode(params)}"
    return _request_get(url)
