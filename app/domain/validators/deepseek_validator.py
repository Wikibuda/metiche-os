from __future__ import annotations

from app.core.config import settings
from app.domain.validators.base import BaseValidator, ValidationResult


class DeepseekValidator(BaseValidator):
    channel = "deepseek"

    def validate(self, task_title: str, task_description: str) -> ValidationResult:
        if not settings.deepseek_api_key:
            return ValidationResult(channel=self.channel, passed=False, detail="Falta DEEPSEEK_API_KEY", critical=True)
        url = f"{settings.deepseek_base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {settings.deepseek_api_key}"}
        ok, status, data, err = self._request_json("GET", url, None, headers=headers)
        if ok:
            model_count = len(data.get("data", [])) if isinstance(data, dict) else 0
            return ValidationResult(channel=self.channel, passed=True, detail=f"DeepSeek disponible ({model_count} modelos)", metadata={"status": status})
        return ValidationResult(channel=self.channel, passed=False, detail=f"DeepSeek no disponible: {err}", critical=True, metadata={"status": status})
