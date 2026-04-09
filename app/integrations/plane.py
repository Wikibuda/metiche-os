from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from app.core.config import settings


@dataclass
class PlaneResponse:
    ok: bool
    status_code: int
    data: dict[str, Any]
    error: str | None = None


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
    base = _issues_base_url()
    if not settings.plane_sync_enabled:
        return PlaneResponse(ok=False, status_code=0, data={}, error="plane_sync_enabled=false")
    if not base:
        return PlaneResponse(ok=False, status_code=0, data={}, error="Plane base URL no configurada")
    return _request_json("PATCH", f"{base}/{issue_id}", fields)


def comment_on_issue(issue_id: str, comment: str) -> PlaneResponse:
    base = _issues_base_url()
    if not settings.plane_sync_enabled:
        return PlaneResponse(ok=False, status_code=0, data={}, error="plane_sync_enabled=false")
    if not base:
        return PlaneResponse(ok=False, status_code=0, data={}, error="Plane base URL no configurada")
    comments_url = f"{base}/{issue_id}/comments"
    return _request_json("POST", comments_url, {"comment_html": comment})
