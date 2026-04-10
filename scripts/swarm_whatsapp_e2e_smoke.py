from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient


def main() -> None:
    db_path = Path(__file__).resolve().parent.parent / "data" / "db" / "swarm_whatsapp_e2e_smoke.db"
    if db_path.exists():
        db_path.unlink()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from app.integrations.whatsapp_adapter import WhatsAppAdapter
    from app.main import app

    client_key = "+5210000000000"
    objective = "Mensaje de prueba del enjambre para confirmar entrega"
    original_send = WhatsAppAdapter.send_message
    send_counter = {"calls": 0}

    def flaky_send_once(self, message):  # type: ignore[no-untyped-def]
        send_counter["calls"] += 1
        if send_counter["calls"] == 1:
            raise TimeoutError("simulated_timeout_first_attempt")
        return original_send(self, message)

    WhatsAppAdapter.send_message = flaky_send_once  # type: ignore[assignment]

    try:
        with TestClient(app) as client:
            seed_memory = client.post(
                f"/channel-memory/{client_key}",
                headers={"X-Channel-Name": "whatsapp"},
                json={"context": {"conversation_state": "active", "last_step": 1}},
            )
            assert seed_memory.status_code == 200, seed_memory.text

            create_swarm = client.post(
                "/swarm",
                json={
                    "name": "Swarm WhatsApp E2E",
                    "goal": "Enviar una confirmacion al usuario por whatsapp",
                    "policy": "narrative-consensus",
                    "agents": ["whatsapp"],
                },
            )
            assert create_swarm.status_code == 200, create_swarm.text
            swarm_id = create_swarm.json()["id"]

            run = client.post(
                f"/swarm/{swarm_id}/run",
                json={"objective": objective, "max_cycles": 1, "client_key": client_key},
            )
            assert run.status_code == 200, run.text
            run_payload = run.json()
            assert run_payload["decision"] == "accept", run_payload

            history = client.get(f"/swarm/{swarm_id}/history")
            assert history.status_code == 200, history.text
            history_payload = history.json()
            assert history_payload["total_cycles"] >= 1, history_payload
            last_cycle = history_payload["cycles"][-1]
            outcome = last_cycle.get("outcome") or ""
            assert "dispatch=whatsapp:ok(r1)" in outcome, last_cycle

            votes = last_cycle.get("votes") or []
            whatsapp_vote = next((vote for vote in votes if vote.get("agent_name") == "whatsapp"), None)
            assert whatsapp_vote is not None, votes
            assert whatsapp_vote.get("vote") == "accept", whatsapp_vote

            memory_after = client.get(f"/channel-memory/{client_key}?channel=whatsapp")
            assert memory_after.status_code == 200, memory_after.text
            memory_payload = memory_after.json()
            assert memory_payload["context"]["last_outbound_message"] == objective, memory_payload

            narratives = client.get("/narrative")
            assert narratives.status_code == 200, narratives.text
            narrative_items = narratives.json()
            assert any("Swarm WhatsApp E2E ciclo" in item["title"] for item in narrative_items), narrative_items
    finally:
        WhatsAppAdapter.send_message = original_send  # type: ignore[assignment]

    print("SMOKE_OK swarm_whatsapp_e2e", {"swarm_id": swarm_id, "decision": run_payload["decision"]})


if __name__ == "__main__":
    main()
