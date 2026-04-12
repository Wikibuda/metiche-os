from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient


def _extract_selected_channels(outcome: str) -> list[str]:
    marker = "selected="
    if marker not in outcome:
        return []
    fragment = outcome.split(marker, 1)[1]
    value = fragment.split(" ", 1)[0].strip()
    if not value or value == "none":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    db_path = Path(__file__).resolve().parent.parent / "data" / "db" / "swarm_multichannel_e2e_smoke.db"
    if db_path.exists():
        db_path.unlink()

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["WHATSAPP_ALLOWED_NUMBERS"] = "123456789,+5210000000000"
    os.environ["WHATSAPP_SANDBOX_MODE"] = "true"
    os.environ["TELEGRAM_ALLOWED_IDS"] = "123456789,987654321"
    os.environ["TELEGRAM_SANDBOX_MODE"] = "true"

    from app.main import app

    client_key = "123456789"
    objective = "Coordinar respuesta conjunta de WhatsApp y Telegram ante incidente operativo"

    with TestClient(app) as client:
        create_swarm = client.post(
            "/swarm",
            json={
                "name": "Swarm Multi Canal E2E",
                "goal": "Sincronizar comunicacion de soporte entre canales",
                "policy": "narrative-consensus",
                "agents": ["whatsapp", "telegram"],
            },
        )
        assert create_swarm.status_code == 200, create_swarm.text
        swarm_id = create_swarm.json()["id"]

        run = client.post(
            f"/swarm/{swarm_id}/run",
            json={
                "objective": objective,
                "max_cycles": 1,
                "client_key": client_key,
            },
        )
        assert run.status_code == 200, run.text
        run_payload = run.json()
        assert run_payload["cycles_executed"] >= 1, run_payload

        history = client.get(f"/swarm/{swarm_id}/history")
        assert history.status_code == 200, history.text
        history_payload = history.json()
        last_cycle = history_payload["cycles"][-1]
        outcome = str(last_cycle.get("outcome") or "")
        selected_channels = _extract_selected_channels(outcome)
        assert selected_channels, {"outcome": outcome, "history": history_payload}

        votes = last_cycle.get("votes") or []
        votes_by_agent = {str(item.get("agent_name")): str(item.get("vote")) for item in votes}
        for channel in ("whatsapp", "telegram"):
            assert channel in votes_by_agent, votes
            if channel in selected_channels:
                assert votes_by_agent[channel] == "accept", votes_by_agent
            else:
                assert votes_by_agent[channel] == "abstain", votes_by_agent

        status = client.get("/dashboard/channels/status?event_preview_limit=5")
        assert status.status_code == 200, status.text
        status_payload = status.json()
        status_map = {item["channel"]: item for item in status_payload.get("channels", [])}
        for selected in selected_channels:
            assert selected in status_map, status_payload
            assert status_map[selected]["status"] == "green", status_map[selected]

        events_count: dict[str, int] = {}
        for selected in selected_channels:
            events_resp = client.get(f"/dashboard/channels/events?channel={selected}&limit=10")
            assert events_resp.status_code == 200, events_resp.text
            items = events_resp.json().get("items", [])
            assert any(str(item.get("event_type") or "").endswith("_send_message") for item in items), items
            events_count[selected] = len(items)

        narratives = client.get("/narrative")
        assert narratives.status_code == 200, narratives.text
        narrative_items = narratives.json()
        swarm_narrative = next(
            (item for item in narrative_items if "Swarm Multi Canal E2E ciclo" in str(item.get("title") or "")),
            None,
        )
        assert swarm_narrative is not None, narrative_items
        body = str(swarm_narrative.get("body") or "")
        assert "Canales seleccionados" in body, body
        for selected in selected_channels:
            assert selected in body, body

    print(
        "SMOKE_OK swarm_multichannel_e2e",
        {
            "swarm_id": swarm_id,
            "decision": run_payload["decision"],
            "selected_channels": selected_channels,
            "events_count": events_count,
        },
    )


if __name__ == "__main__":
    main()
