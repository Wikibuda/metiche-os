from __future__ import annotations

from app.core.config import settings
from app.domain.validators.base import BaseValidator, ValidationResult


class DashboardValidator(BaseValidator):
    channel = "dashboard"

    def validate(self, task_title: str, task_description: str) -> ValidationResult:
        health_url = settings.dashboard_health_url
        if not health_url and settings.dashboard_port:
            health_url = f"http://127.0.0.1:{settings.dashboard_port}/health"
        if not health_url:
            return ValidationResult(channel=self.channel, passed=False, detail="Falta DASHBOARD_HEALTH_URL o DASHBOARD_PORT", metadata={})
        headers = {}
        if settings.dashboard_health_token:
            headers["Authorization"] = f"Bearer {settings.dashboard_health_token}"
        ok, status, data, err = self._request_json("GET", health_url, None, headers=headers)
        if ok:
            return ValidationResult(channel=self.channel, passed=True, detail="Dashboard healthy", metadata={"status": status, "response": data})
        return ValidationResult(channel=self.channel, passed=False, detail=f"Dashboard no responde: {err}", metadata={"status": status}, critical=False)
