from __future__ import annotations

from app.core.config import settings
from app.domain.validators.base import BaseValidator, ValidationResult


class TelegramValidator(BaseValidator):
    channel = "telegram"

    def validate(self, task_title: str, task_description: str) -> ValidationResult:
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            if settings.telegram_user_id and settings.telegram_username:
                return ValidationResult(
                    channel=self.channel,
                    passed=True,
                    detail="Telegram identificado por TELEGRAM_USER_ID/TELEGRAM_USERNAME (modo metadata).",
                    metadata={"user_id": settings.telegram_user_id, "username": settings.telegram_username},
                )
            return ValidationResult(
                channel=self.channel,
                passed=False,
                detail="Faltan TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID o TELEGRAM_USER_ID/TELEGRAM_USERNAME",
                critical=True,
            )
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {"chat_id": settings.telegram_chat_id, "text": f"[metiche] healthcheck: {task_title}"}
        ok, status, data, err = self._request_json("POST", url, payload)
        if ok and data.get("ok"):
            return ValidationResult(channel=self.channel, passed=True, detail="Mensaje de prueba enviado", metadata={"status": status})
        return ValidationResult(channel=self.channel, passed=False, detail=f"Telegram no disponible: {err or data}", critical=True, metadata={"status": status})
