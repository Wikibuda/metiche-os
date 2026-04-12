from __future__ import annotations

import os
import re
from typing import Any

import httpx


def _required_env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _validate_phone_format_or_raise(phone_number: str) -> str:
    cleaned = (phone_number or "").strip()
    if not re.fullmatch(r"\+521\d{10}", cleaned):
        raise ValueError("Formato invalido: usa +521<numero-de-telefono> (10 digitos).")
    return cleaned


def _assert_ok(response: httpx.Response, label: str) -> dict[str, Any]:
    if response.status_code != 200:
        raise RuntimeError(f"{label}_failed:{response.status_code}:{response.text}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label}_invalid_payload:{payload!r}")
    return payload


def main() -> None:
    api_base_url = _required_env("METICHE_API_BASE_URL", "http://127.0.0.1:8091").rstrip("/")
    target_phone = _validate_phone_format_or_raise(
        _required_env("WHATSAPP_REAL_TARGET", "+5210000000000")
    )
    test_message = _required_env(
        "WHATSAPP_REAL_MESSAGE",
        "Hola, esto es una prueba del enjambre de Metiche (live api)",
    )
    timeout = float(_required_env("SMOKE_HTTP_TIMEOUT_SECONDS", "30"))

    with httpx.Client(base_url=api_base_url, timeout=timeout) as client:
        health = client.get("/health")
        if health.status_code != 200:
            raise RuntimeError(f"api_health_failed:{health.status_code}:{health.text}")

        seed_memory = client.post(
            f"/channel-memory/{target_phone}",
            headers={"X-Channel-Name": "whatsapp"},
            json={"context": {"conversation_state": "active", "source": "whatsapp_real_smoke_live"}},
        )
        _assert_ok(seed_memory, "seed_memory")

        create_swarm = client.post(
            "/swarm",
            json={
                "name": "Swarm WhatsApp Real Smoke Live",
                "goal": "Enviar un mensaje real por WhatsApp desde API viva",
                "policy": "narrative-consensus",
                "agents": ["whatsapp"],
            },
        )
        swarm_payload = _assert_ok(create_swarm, "create_swarm")
        swarm_id = str(swarm_payload["id"])

        run = client.post(
            f"/swarm/{swarm_id}/run",
            json={"objective": test_message, "max_cycles": 1, "client_key": target_phone},
        )
        run_payload = _assert_ok(run, "run_swarm")
        if run_payload.get("decision") != "accept":
            raise RuntimeError(f"swarm_rejected:{run_payload}")

        history = client.get(f"/swarm/{swarm_id}/history")
        history_payload = _assert_ok(history, "history")
        cycles = history_payload.get("cycles") or []
        if not cycles:
            raise RuntimeError(f"history_without_cycles:{history_payload}")
        last_cycle = cycles[-1]
        outcome = str(last_cycle.get("outcome") or "")
        if "dispatch=whatsapp:ok" not in outcome:
            raise RuntimeError(f"dispatch_not_ok:{last_cycle}")

        events = client.get("/dashboard/channels/events?channel=whatsapp&limit=100")
        events_payload = _assert_ok(events, "events")
        items = events_payload.get("items") or []
        send_event = next(
            (
                item
                for item in items
                if item.get("event_type") == "whatsapp_send_message"
                and str((item.get("payload") or {}).get("client_key")) == target_phone
                and str((item.get("payload") or {}).get("text")) == test_message
            ),
            None,
        )
        if send_event is None:
            raise RuntimeError(f"send_event_not_found:{items}")
        send_payload = send_event.get("payload") or {}
        if bool(send_payload.get("success")) is not True:
            raise RuntimeError(f"send_event_failed:{send_payload}")

        memory_after = client.get(f"/channel-memory/{target_phone}?channel=whatsapp")
        memory_payload = _assert_ok(memory_after, "memory_after")
        context = memory_payload.get("context") or {}
        if context.get("last_outbound_message") != test_message:
            raise RuntimeError(f"memory_not_updated:{memory_payload}")

    print(
        "SMOKE_OK whatsapp_real_live",
        {
            "api_base_url": api_base_url,
            "target_phone": target_phone,
            "swarm_id": swarm_id,
            "message": test_message,
            "note": "Este rastro debe verse en War Room / Consola de Enjambres.",
        },
    )


if __name__ == "__main__":
    main()
