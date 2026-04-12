from __future__ import annotations

import json

from sqlmodel import Session

from app.core.db import create_db_and_tables, engine
from app.services.channel_memory_service import ChannelMemoryService


def main() -> int:
    create_db_and_tables()
    with Session(engine) as session:
        service = ChannelMemoryService(session)

        expected_whatsapp = {"last_message": "Hola Metiche", "intent": "saludo", "step": 1}
        expected_telegram = {"last_message": "Seguimos por Telegram", "intent": "seguimiento", "step": 2}

        service.save_context(client_key="test_user", channel="whatsapp", context=expected_whatsapp)
        loaded_whatsapp = service.get_context(client_key="test_user", channel="whatsapp")
        if loaded_whatsapp != expected_whatsapp:
            raise RuntimeError("Smoke fallido: contexto de whatsapp no coincide")

        # Mismo client_key, segundo canal para validar consistencia cross-channel.
        service.save_context(client_key="test_user", channel="telegram", context=expected_telegram)
        loaded_telegram = service.get_context(client_key="test_user", channel="telegram")
        if loaded_telegram != expected_telegram:
            raise RuntimeError("Smoke fallido: contexto de telegram no coincide")

        print("SMOKE_OK channel_memory")
        print(
            json.dumps(
                {
                    "client_key": "test_user",
                    "whatsapp": loaded_whatsapp,
                    "telegram": loaded_telegram,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
