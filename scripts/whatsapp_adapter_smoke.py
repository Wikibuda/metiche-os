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
    os.environ["WHATSAPP_ALLOWED_NUMBERS"] = "+5210000000000,+5210000000001"
    os.environ["WHATSAPP_SANDBOX_MODE"] = "true"

    from app.core.db import engine
    from app.integrations.whatsapp_adapter import IncomingWhatsAppMessage, OutboundWhatsAppMessage, WhatsAppAdapter
    from app.main import app

    client_key = "+5210000000000"
    unauthorized_number = "+5212345678901"
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

            outbound = adapter.send_message(OutboundWhatsAppMessage(client_key=client_key, text="Confirmado, reviso tu caso"))
            assert outbound["success"] is True, outbound
            assert outbound["payload"]["sandbox"] is True, outbound

            try:
                adapter.send_message(OutboundWhatsAppMessage(client_key=unauthorized_number, text="Mensaje bloqueado"))
                raise AssertionError("expected security block for unauthorized number")
            except PermissionError as exc:
                assert "phone_number_not_allowed" in str(exc), exc

            after = client.get(f"/channel-memory/{client_key}?channel=whatsapp")
            assert after.status_code == 200, after.text
            after_payload = after.json()
            assert after_payload["context"]["last_user_message"] == "Hola, sigo esperando mi pedido", after_payload

            inbound_event_types = session.connection().execute(
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
            normalized_inbound = [row[0] for row in inbound_event_types]
            assert "whatsapp_memory_read" in normalized_inbound, normalized_inbound
            assert "whatsapp_memory_write" in normalized_inbound, normalized_inbound

            outbound_event_types = session.connection().execute(
                text(
                    """
                    SELECT event_type
                    FROM task_events
                    WHERE task_id = :task_id
                    ORDER BY occurred_at ASC
                    """
                ),
                {"task_id": outbound["trace_task_id"]},
            ).fetchall()
            normalized_outbound = [row[0] for row in outbound_event_types]
            assert "whatsapp_sandbox_mode" in normalized_outbound, normalized_outbound
            assert "whatsapp_send_message" in normalized_outbound, normalized_outbound

            security_blocks = session.connection().execute(
                text(
                    """
                    SELECT COUNT(1)
                    FROM task_events
                    WHERE event_type = 'whatsapp_security_block'
                    """
                )
            ).scalar_one()
            assert security_blocks >= 1, security_blocks

    print(
        "SMOKE_OK whatsapp_adapter",
        {
            "client_key": client_key,
            "sandbox_mode": True,
            "checks": ["safelist_block", "sandbox_simulation", "memory_read_write_events"],
        },
    )


if __name__ == "__main__":
    main()
