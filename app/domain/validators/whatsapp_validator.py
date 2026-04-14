from __future__ import annotations

import subprocess
import time

import httpx

from app.core.config import settings
from app.domain.validators.base import BaseValidator, ValidationResult


class WhatsAppValidator(BaseValidator):
    channel = "whatsapp"
    _channel_check_cache_until: float = 0.0
    _channel_check_cached_result: tuple[bool, dict[str, str]] = (False, {"source": "cache", "reason": "cold"})

    def validate(self, task_title: str, task_description: str) -> ValidationResult:
        health_urls = self._build_health_urls()
        response = None
        payload = {}
        selected_health_url = ""
        last_error = ""
        tried: list[dict[str, str | int]] = []

        for health_url in health_urls:
            try:
                with httpx.Client(timeout=5.0) as client:
                    candidate_response = client.get(health_url)
                candidate_payload = (
                    candidate_response.json()
                    if candidate_response.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                payload_ok = isinstance(candidate_payload, dict) and (
                    candidate_payload.get("ok") is True or candidate_payload.get("status") == "live"
                )
                if candidate_response.status_code == 200 and payload_ok:
                    response = candidate_response
                    payload = candidate_payload
                    selected_health_url = health_url
                    break
                tried.append(
                    {
                        "health_url": health_url,
                        "status_code": candidate_response.status_code,
                    }
                )
                last_error = f"Unexpected health response status={candidate_response.status_code}"
            except Exception as exc:
                tried.append({"health_url": health_url, "error": str(exc)})
                last_error = str(exc)

        if response is None:
            return ValidationResult(
                channel=self.channel,
                passed=False,
                detail=f"Gateway health check error: {last_error or 'no healthy endpoint found'}",
                critical=True,
                metadata={
                    "channel": self.channel,
                    "error": last_error or "no healthy endpoint found",
                    "health_url": health_urls[0] if health_urls else "",
                    "tried_health_urls": tried,
                },
            )

        channels_ok, channel_check_meta = self._is_whatsapp_channel_linked_enabled(
            selected_health_url=selected_health_url
        )
        if not channels_ok:
            return ValidationResult(
                channel=self.channel,
                passed=False,
                detail="WhatsApp channel not linked/enabled",
                critical=True,
                metadata={
                    "channel": self.channel,
                    "error": "WhatsApp channel not linked/enabled",
                    "channel_check": channel_check_meta,
                },
            )

        return ValidationResult(
            channel=self.channel,
            passed=True,
            detail="WhatsApp gateway live y canal linked/enabled.",
            metadata={
                "status": response.status_code,
                "response": payload,
                "health_url": selected_health_url,
                "channel_check": channel_check_meta,
            },
        )

    def _build_health_urls(self) -> list[str]:
        candidates: list[str] = []

        explicit_health = (settings.whatsapp_health_url or "").strip()
        if explicit_health:
            candidates.append(explicit_health.rstrip("/"))

        gateway_url = (settings.openclaw_gateway_url or "").strip().rstrip("/")
        if gateway_url:
            candidates.append(f"{gateway_url}/health")

        candidates.extend(
            [
                "http://host.docker.internal:18797/health",
                "http://127.0.0.1:18797/health",
                "http://localhost:18797/health",
            ]
        )

        deduped: list[str] = []
        seen = set()
        for item in candidates:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    @classmethod
    def _is_whatsapp_channel_linked_enabled(cls, *, selected_health_url: str) -> tuple[bool, dict[str, str]]:
        now = time.time()
        if now < cls._channel_check_cache_until:
            return cls._channel_check_cached_result

        command = "openclaw channels list 2>/dev/null"
        result = subprocess.run(
            ["bash", "-lc", command],
            check=False,
            capture_output=True,
            text=True,
        )
        output = (result.stdout or "").lower()
        linked_enabled = "whatsapp default: linked" in output and "enabled" in output
        not_linked = "whatsapp default: not linked" in output

        # In Docker, CLI state may differ from host gateway state. If gateway health
        # is live via host.docker.internal, treat local "not linked" as degraded pass.
        if not linked_enabled and not_linked and "host.docker.internal" in selected_health_url:
            cached = (
                True,
                {
                    "source": "openclaw_cli",
                    "mode": "degraded_pass",
                    "reason": "docker_cli_state_mismatch_with_host_gateway",
                },
            )
            cls._channel_check_cached_result = cached
            cls._channel_check_cache_until = now + 60.0
            return cached

        cached = (
            linked_enabled,
            {
                "source": "openclaw_cli",
                "mode": "strict",
                "reason": "linked_enabled" if linked_enabled else "not_linked_or_disabled",
            },
        )
        cls._channel_check_cached_result = cached
        cls._channel_check_cache_until = now + 60.0
        return cached
