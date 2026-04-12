from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session


def _merge_allowed_numbers(raw: str, required_number: str) -> str:
    ordered: list[str] = []
    seen: set[str] = set()
    for token in (raw or "").split(","):
        item = token.strip()
        if not item or item in seen:
            continue
        ordered.append(item)
        seen.add(item)
    if required_number not in seen:
        ordered.append(required_number)
    return ",".join(ordered)


def _load_gateway_token() -> str:
    explicit = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if explicit:
        return explicit
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if not config_path.exists():
        return ""
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        token = str(payload.get("gateway", {}).get("auth", {}).get("token", "")).strip()
        return token
    except Exception:
        return ""


def _validate_phone_format_or_raise(phone_number: str) -> str:
    cleaned = (phone_number or "").strip()
    if not re.fullmatch(r"\+521\d{10}", cleaned):
        raise ValueError("Formato invalido: usa +521<numero-de-telefono> (10 digitos).")
    return cleaned


def main() -> None:
    target_phone = _validate_phone_format_or_raise(
        os.environ.get("WHATSAPP_REAL_TARGET", "+5210000000000")
    )
    test_message = os.environ.get(
        "WHATSAPP_REAL_MESSAGE",
        "Hola, esto es una prueba del enjambre de Metiche",
    ).strip()
    gateway_url = os.environ.get("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18797").strip()

    db_path = Path(__file__).resolve().parent.parent / "data" / "db" / "whatsapp_real_smoke.db"
    if db_path.exists():
        db_path.unlink()

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["WHATSAPP_ALLOWED_NUMBERS"] = _merge_allowed_numbers(
        os.environ.get("WHATSAPP_ALLOWED_NUMBERS", ""),
        target_phone,
    )
    os.environ["WHATSAPP_SANDBOX_MODE"] = "false"
    os.environ["OPENCLAW_GATEWAY_URL"] = gateway_url
    gateway_token = _load_gateway_token()
    if gateway_token:
        os.environ["OPENCLAW_GATEWAY_TOKEN"] = gateway_token

    from app.core.db import engine
    from app.main import app

    with TestClient(app) as client:
        seed_memory = client.post(
            f"/channel-memory/{target_phone}",
            headers={"X-Channel-Name": "whatsapp"},
            json={"context": {"conversation_state": "active", "source": "whatsapp_real_smoke"}},
        )
        assert seed_memory.status_code == 200, seed_memory.text

        create_swarm = client.post(
            "/swarm",
            json={
                "name": "Swarm WhatsApp Real Smoke",
                "goal": "Enviar un mensaje real por WhatsApp",
                "policy": "narrative-consensus",
                "agents": ["whatsapp"],
            },
        )
        assert create_swarm.status_code == 200, create_swarm.text
        swarm_id = create_swarm.json()["id"]

        run = client.post(
            f"/swarm/{swarm_id}/run",
            json={"objective": test_message, "max_cycles": 1, "client_key": target_phone},
        )
        assert run.status_code == 200, run.text
        run_payload = run.json()
        assert run_payload.get("decision") == "accept", run_payload

        history = client.get(f"/swarm/{swarm_id}/history")
        assert history.status_code == 200, history.text
        history_payload = history.json()
        assert history_payload.get("total_cycles", 0) >= 1, history_payload
        last_cycle = history_payload["cycles"][-1]
        outcome = str(last_cycle.get("outcome") or "")
        assert "dispatch=whatsapp:ok" in outcome, last_cycle

        events = client.get("/dashboard/channels/events?channel=whatsapp&limit=50")
        assert events.status_code == 200, events.text
        event_items = events.json().get("items", [])
        send_event = next(
            (
                item
                for item in event_items
                if item.get("event_type") == "whatsapp_send_message"
                and str((item.get("payload") or {}).get("client_key")) == target_phone
                and str((item.get("payload") or {}).get("text")) == test_message
            ),
            None,
        )
        assert send_event is not None, event_items
        send_payload = send_event.get("payload") or {}
        assert bool(send_payload.get("success")) is True, send_payload

        memory_after = client.get(f"/channel-memory/{target_phone}?channel=whatsapp")
        assert memory_after.status_code == 200, memory_after.text
        memory_payload = memory_after.json()
        assert memory_payload.get("context", {}).get("last_outbound_message") == test_message, memory_payload

    with Session(engine) as session:
        memory_count = session.connection().execute(
            text(
                """
                SELECT COUNT(1)
                FROM memory_entries
                WHERE memory_text LIKE :needle
                """
            ),
            {"needle": "%dispatch=whatsapp:ok%"},
        ).scalar_one()
        assert int(memory_count) >= 1, memory_count

    print(
        "SMOKE_OK whatsapp_real",
        {
            "target_phone": target_phone,
            "sandbox_mode": False,
            "swarm_id": swarm_id,
            "message": test_message,
            "gateway_url": gateway_url,
            "note": "Confirma manualmente que el mensaje llego al celular.",
        },
    )


if __name__ == "__main__":
    main()
