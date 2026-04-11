from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session


def main() -> None:
    db_path = Path(__file__).resolve().parent.parent / "data" / "db" / "telegram_adapter_smoke.db"
    if db_path.exists():
        db_path.unlink()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["TELEGRAM_ALLOWED_IDS"] = "123456789,987654321"
    os.environ["TELEGRAM_SANDBOX_MODE"] = "true"

    from app.core.db import engine
    from app.integrations.telegram_adapter import IncomingTelegramMessage, OutboundTelegramMessage, TelegramAdapter
    from app.main import app

    client_key = "123456789"
    unauthorized_id = "555000111"
    seed_context = {"customer_name": "Ada", "last_topic": "seguimiento de ticket", "step": 3}

    with TestClient(app) as client:
        seed = client.post(
            f"/channel-memory/{client_key}",
            headers={"X-Channel-Name": "telegram"},
            json={"context": seed_context},
        )
        assert seed.status_code == 200, seed.text

        with Session(engine) as session:
            adapter = TelegramAdapter(session=session, api_client=client)
            result = adapter.handle_incoming_message(
                IncomingTelegramMessage(chat_id=client_key, text="Hola, sigues con mi ticket?")
            )

            assert result.client_key == client_key, result
            assert result.loaded_context == seed_context, result
            assert "seguimiento de ticket" in result.prompt, result.prompt
            assert "sigues con mi ticket?" in result.prompt, result.prompt
            assert result.updated_context["last_user_message"] == "Hola, sigues con mi ticket?", result.updated_context

            outbound = adapter.send_message(OutboundTelegramMessage(client_key=client_key, text="Si, te comparto avance"))
            assert outbound["success"] is True, outbound
            assert outbound["payload"]["sandbox"] is True, outbound

            try:
                adapter.send_message(OutboundTelegramMessage(client_key=unauthorized_id, text="Mensaje bloqueado"))
                raise AssertionError("expected security block for unauthorized id")
            except PermissionError as exc:
                assert "chat_id_not_allowed" in str(exc), exc

            after = client.get(f"/channel-memory/{client_key}?channel=telegram")
            assert after.status_code == 200, after.text
            after_payload = after.json()
            assert after_payload["context"]["last_user_message"] == "Hola, sigues con mi ticket?", after_payload

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
            assert "telegram_memory_read" in normalized_inbound, normalized_inbound
            assert "telegram_memory_write" in normalized_inbound, normalized_inbound

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
            assert "telegram_sandbox_mode" in normalized_outbound, normalized_outbound
            assert "telegram_send_message" in normalized_outbound, normalized_outbound

            security_blocks = session.connection().execute(
                text(
                    """
                    SELECT COUNT(1)
                    FROM task_events
                    WHERE event_type = 'telegram_security_block'
                    """
                )
            ).scalar_one()
            assert security_blocks >= 1, security_blocks

    print(
        "SMOKE_OK telegram_adapter",
        {
            "client_key": client_key,
            "sandbox_mode": True,
            "checks": ["safelist_block", "sandbox_simulation", "memory_read_write_events"],
        },
    )


if __name__ == "__main__":
    main()
