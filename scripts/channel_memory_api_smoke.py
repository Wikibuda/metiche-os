from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient


def main() -> None:
    db_path = Path(__file__).resolve().parent.parent / "data" / "db" / "channel_memory_api_smoke.db"
    if db_path.exists():
        db_path.unlink()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from app.main import app

    expected_context = {
        "last_message": "Hola desde API",
        "intent": "saludo",
        "step": 1,
        "meta": {"source": "smoke"},
    }

    with TestClient(app) as client:
        post_missing_header = client.post(
            "/channel-memory/test_user",
            json={"channel": "whatsapp", "context": expected_context},
        )
        assert post_missing_header.status_code == 422, post_missing_header.text

        post_resp = client.post(
            "/channel-memory/test_user",
            headers={"X-Channel-Name": "whatsapp"},
            json={"channel": "whatsapp", "context": expected_context},
        )
        assert post_resp.status_code == 200, post_resp.text
        post_payload = post_resp.json()
        assert post_payload["client_key"] == "test_user", post_payload
        assert post_payload["channel"] == "whatsapp", post_payload
        assert post_payload["context"] == expected_context, post_payload

        get_resp = client.get("/channel-memory/test_user?channel=whatsapp")
        assert get_resp.status_code == 200, get_resp.text
        get_payload = get_resp.json()
        assert get_payload["client_key"] == "test_user", get_payload
        assert get_payload["channel"] == "whatsapp", get_payload
        assert get_payload["context"] == expected_context, get_payload

        delete_resp = client.delete("/channel-memory/test_user?channel=whatsapp")
        assert delete_resp.status_code == 204, delete_resp.text

        get_after_delete = client.get("/channel-memory/test_user?channel=whatsapp")
        assert get_after_delete.status_code == 404, get_after_delete.text

        print("SMOKE_OK channel_memory_api", {"client_key": "test_user", "channel": "whatsapp"})


if __name__ == "__main__":
    main()
