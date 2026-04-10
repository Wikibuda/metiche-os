import os
from pathlib import Path

from fastapi.testclient import TestClient


def main() -> None:
    db_path = Path(__file__).resolve().parent.parent / "data" / "db" / "swarm_dashboard_test.db"
    if db_path.exists():
        db_path.unlink()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from app.main import app

    with TestClient(app) as client:
        create = client.post(
            "/swarm",
            json={
                "name": "Swarm Dashboard WhatsApp+Shopify",
                "goal": "Coordinar respuesta de whatsapp y shopify ante incidente",
                "policy": "narrative-consensus",
                "agents": ["whatsapp", "shopify"],
            },
        )
        assert create.status_code == 200, create.text
        swarm_id = create.json()["id"]

        run = client.post(
            f"/swarm/{swarm_id}/run",
            json={
                "objective": "Proteger ventas y soporte",
                "max_cycles": 3,
                "client_key": "war-room-ui",
            },
        )
        assert run.status_code == 200, run.text

        listed = client.get("/swarm?limit=10")
        assert listed.status_code == 200, listed.text
        listed_payload = listed.json()
        assert any(item["id"] == swarm_id for item in listed_payload), listed_payload

        history = client.get(f"/swarm/{swarm_id}/history")
        assert history.status_code == 200, history.text
        history_payload = history.json()

        print(
            "OK dashboard endpoints:",
            {
                "swarm_id": swarm_id,
                "listed": len(listed_payload),
                "cycles": history_payload["total_cycles"],
            },
        )


if __name__ == "__main__":
    main()
