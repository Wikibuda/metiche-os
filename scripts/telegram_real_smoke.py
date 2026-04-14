from __future__ import annotations

import os
from typing import Any

import httpx


def _validate_chat_id_or_raise(chat_id: str) -> str:
    cleaned = (chat_id or "").strip()
    if not cleaned or not cleaned.lstrip("-").isdigit():
        raise ValueError("TELEGRAM_REAL_TARGET debe ser un chat_id numerico valido.")
    return cleaned


def _required_env(name: str, default: str) -> str:
    value = os.environ.get(name, default).strip()
    if not value:
        raise RuntimeError(f"Falta variable requerida: {name}")
    return value


def _assert_ok(response: httpx.Response, label: str) -> dict[str, Any]:
    if response.status_code != 200:
        raise RuntimeError(f"{label}_failed:{response.status_code}:{response.text}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label}_invalid_payload:{payload!r}")
    return payload


def main() -> None:
    api_base_url = _required_env("METICHE_API_BASE_URL", "http://127.0.0.1:8091").rstrip("/")
    target_chat_id = _validate_chat_id_or_raise(
        os.environ.get("TELEGRAM_REAL_TARGET")
        or os.environ.get("TELEGRAM_CHAT_ID")
        or os.environ.get("TELEGRAM_USER_ID")
        or ""
    )
    test_message = os.environ.get(
        "TELEGRAM_REAL_MESSAGE",
        "Hola, esto es una prueba del enjambre de Metiche desde Telegram",
    ).strip()
    timeout = float(_required_env("SMOKE_HTTP_TIMEOUT_SECONDS", "35"))

    with httpx.Client(base_url=api_base_url, timeout=timeout) as client:
        health = client.get("/health")
        if health.status_code != 200:
            raise RuntimeError(f"api_health_failed:{health.status_code}:{health.text}")

        seed_memory = client.post(
            f"/channel-memory/{target_chat_id}",
            headers={"X-Channel-Name": "telegram"},
            json={"context": {"conversation_state": "active", "source": "telegram_real_smoke"}},
        )
        _assert_ok(seed_memory, "seed_memory")

        create_swarm = client.post(
            "/swarm",
            json={
                "name": "Swarm Telegram Real Smoke",
                "goal": "Enviar un mensaje real por Telegram",
                "policy": "narrative-consensus",
                "agents": ["telegram"],
            },
        )
        swarm_payload = _assert_ok(create_swarm, "create_swarm")
        swarm_id = str(swarm_payload["id"])

        run = client.post(
            f"/swarm/{swarm_id}/run",
            json={"objective": test_message, "max_cycles": 1, "client_key": target_chat_id},
        )
        run_payload = _assert_ok(run, "run_swarm")
        if run_payload.get("decision") != "accept":
            raise RuntimeError(f"swarm_rejected:{run_payload}")

        history = client.get(f"/swarm/{swarm_id}/history")
        history_payload = _assert_ok(history, "history")
        if int(history_payload.get("total_cycles", 0)) < 1:
            raise RuntimeError(f"history_without_cycles:{history_payload}")
        last_cycle = history_payload["cycles"][-1]
        outcome = str(last_cycle.get("outcome") or "")
        if "dispatch=telegram:ok" not in outcome:
            raise RuntimeError(f"dispatch_not_ok:{last_cycle}")

        events = client.get("/dashboard/channels/events?channel=telegram&limit=80")
        events_payload = _assert_ok(events, "events")
        event_items = events_payload.get("items", [])
        send_event = next(
            (
                item
                for item in event_items
                if item.get("event_type") == "telegram_send_message"
                and str((item.get("payload") or {}).get("client_key")) == target_chat_id
                and str((item.get("payload") or {}).get("text")) == test_message
            ),
            None,
        )
        if send_event is None:
            raise RuntimeError(f"send_event_not_found:{event_items}")
        send_payload = send_event.get("payload") or {}
        if bool(send_payload.get("success")) is not True:
            raise RuntimeError(f"send_event_failed:{send_payload}")
        result_payload = send_payload.get("result") or {}
        if bool(result_payload.get("sandbox")):
            raise RuntimeError(f"telegram_sandbox_detected:{result_payload}")

        memory_after = client.get(f"/channel-memory/{target_chat_id}?channel=telegram")
        memory_payload = _assert_ok(memory_after, "memory_after")
        if memory_payload.get("context", {}).get("last_outbound_message") != test_message:
            raise RuntimeError(f"memory_not_updated:{memory_payload}")

        narratives = client.get("/narrative?limit=25")
        if narratives.status_code != 200:
            raise RuntimeError(f"narrative_failed:{narratives.status_code}:{narratives.text}")
        narrative_items = narratives.json()
        matching_narrative = next(
            (item for item in narrative_items if f"Swarm Telegram Real Smoke ciclo" in str(item.get("title") or "")),
            None,
        )
        if matching_narrative is None:
            raise RuntimeError(f"narrative_not_found:{narrative_items}")

    print(
        "SMOKE_OK telegram_real",
        {
            "api_base_url": api_base_url,
            "target_chat_id": target_chat_id,
            "swarm_id": swarm_id,
            "message": test_message,
            "note": "Confirma manualmente que el mensaje llego en Telegram (chat destino).",
        },
    )


if __name__ == "__main__":
    main()
