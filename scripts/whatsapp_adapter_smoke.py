from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session


def main() -> None:
    db_path = Path(__file__).resolve().parent.parent / "data" / "db" / "whatsapp_adapter_smoke.db"
    if db_path.exists():
        db_path.unlink()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from app.core.db import engine
    from app.integrations.whatsapp_adapter import IncomingWhatsAppMessage, WhatsAppAdapter
    from app.main import app

    client_key = "+5210000000000"
    seed_context = {"customer_name": "Ada", "last_topic": "pedido retrasado", "step": 2}

    with TestClient(app) as client:
        seed = client.post(
            f"/channel-memory/{client_key}",
            headers={"X-Channel-Name": "whatsapp"},
            json={"context": seed_context},
        )
        assert seed.status_code == 200, seed.text

        with Session(engine) as session:
            adapter = WhatsAppAdapter(session=session, api_client=client)
            result = adapter.handle_incoming_message(
                IncomingWhatsAppMessage(phone_number=client_key, text="Hola, sigo esperando mi pedido")
            )

            assert result.client_key == client_key, result
            assert result.loaded_context == seed_context, result
            assert "pedido retrasado" in result.prompt, result.prompt
            assert "sigo esperando mi pedido" in result.prompt, result.prompt
            assert result.updated_context["last_user_message"] == "Hola, sigo esperando mi pedido", result.updated_context

            after = client.get(f"/channel-memory/{client_key}?channel=whatsapp")
            assert after.status_code == 200, after.text
            after_payload = after.json()
            assert after_payload["context"]["last_user_message"] == "Hola, sigo esperando mi pedido", after_payload

            event_types = session.connection().execute(
                text(
                    """
                    SELECT event_type
                    FROM task_events
                    WHERE task_id = :task_id
                    ORDER BY occurred_at ASC
                    """
                ),
                {"task_id": result.trace_task_id},
            ).fetchall()
            normalized = [row[0] for row in event_types]
            assert "whatsapp_memory_read" in normalized, normalized
            assert "whatsapp_memory_write" in normalized, normalized

    print("SMOKE_OK whatsapp_adapter", {"client_key": client_key, "events": ["whatsapp_memory_read", "whatsapp_memory_write"]})


if __name__ == "__main__":
    main()
