from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from app.core.config import settings


@dataclass
class ValidationResult:
    channel: str
    passed: bool
    detail: str
    critical: bool = False
    metadata: dict[str, Any] | None = None


class BaseValidator:
    channel: str = "unknown"

    def validate(self, task_title: str, task_description: str) -> ValidationResult:
        raise NotImplementedError

    def _request_json(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[bool, int, dict[str, Any], str]:
        req_headers = {"Content-Type": "application/json", **(headers or {})}
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(url=url, data=body, headers=req_headers, method=method)
        try:
            with request.urlopen(req, timeout=settings.validation_timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                parsed = json.loads(raw) if raw else {}
                return True, resp.getcode(), parsed, ""
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            return False, exc.code, {}, raw or str(exc)
        except Exception as exc:  # pragma: no cover - defensive
            return False, 0, {}, str(exc)
