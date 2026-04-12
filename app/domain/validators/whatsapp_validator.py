from __future__ import annotations

import subprocess
import time

import httpx

from app.core.config import settings
from app.domain.validators.base import BaseValidator, ValidationResult


class WhatsAppValidator(BaseValidator):
    channel = "whatsapp"
    _channel_check_cache_until: float = 0.0
    _channel_check_cached_passed: bool = False

    def validate(self, task_title: str, task_description: str) -> ValidationResult:
        gateway_url = (settings.openclaw_gateway_url or "http://127.0.0.1:18797").rstrip("/")
        health_url = f"{gateway_url}/health"

        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(health_url)
            payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        except Exception as exc:
            return ValidationResult(
                channel=self.channel,
                passed=False,
                detail=f"Gateway health check error: {exc}",
                critical=True,
                metadata={"channel": self.channel, "error": str(exc), "health_url": health_url},
            )

        payload_ok = isinstance(payload, dict) and (payload.get("ok") is True or payload.get("status") == "live")
        if response.status_code != 200 or not payload_ok:
            return ValidationResult(
                channel=self.channel,
                passed=False,
                detail="Gateway health check failed",
                critical=True,
                metadata={
                    "channel": self.channel,
                    "error": f"Unexpected health response status={response.status_code}",
                    "health_url": health_url,
                    "response": payload,
                },
            )

        channels_ok = self._is_whatsapp_channel_linked_enabled()
        if not channels_ok:
            return ValidationResult(
                channel=self.channel,
                passed=False,
                detail="WhatsApp channel not linked/enabled",
                critical=True,
                metadata={"channel": self.channel, "error": "WhatsApp channel not linked/enabled"},
            )

        return ValidationResult(
            channel=self.channel,
            passed=True,
            detail="WhatsApp gateway live y canal linked/enabled.",
            metadata={"status": response.status_code, "response": payload, "gateway_url": gateway_url},
        )

    @classmethod
    def _is_whatsapp_channel_linked_enabled(cls) -> bool:
        now = time.time()
        if now < cls._channel_check_cache_until:
            return cls._channel_check_cached_passed

        command = 'openclaw channels list 2>/dev/null | grep -q "WhatsApp default: linked, enabled"'
        result = subprocess.run(
            ["bash", "-lc", command],
            check=False,
            capture_output=True,
            text=True,
        )
        passed = result.returncode == 0
        cls._channel_check_cached_passed = passed
        cls._channel_check_cache_until = now + 60.0
        return passed
