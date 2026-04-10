import os
from pathlib import Path

from fastapi.testclient import TestClient


def main() -> None:
    db_path = Path(__file__).resolve().parent.parent / "data" / "db" / "swarm_integration_test.db"
    if db_path.exists():
        db_path.unlink()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from app.main import app

    with TestClient(app) as client:
        create_payload = {
            "name": "Swarm Integracion Semana2",
            "goal": "Orquestar decisiones de enjambre con trazabilidad por ciclos",
            "policy": "narrative-consensus",
            "agents": ["telegram", "dashboard", "deepseek"],
        }
        create_res = client.post("/swarm", json=create_payload)
        assert create_res.status_code == 200, create_res.text
        swarm_id = create_res.json()["id"]

        run_res = client.post(
            f"/swarm/{swarm_id}/run",
            json={
                "objective": "Hay riesgo operativo alto en despliegue nocturno",
                "max_cycles": 3,
                "client_key": "it-smoke",
            },
        )
        assert run_res.status_code == 200, run_res.text
        run_data = run_res.json()
        assert run_data["cycles_executed"] == 2, run_data
        assert run_data["stop_reason"] == "reject_streak", run_data

        history_res = client.get(f"/swarm/{swarm_id}/history")
        assert history_res.status_code == 200, history_res.text
        history_data = history_res.json()
        assert history_data["total_cycles"] == 2, history_data
        assert len(history_data["cycles"]) == 2, history_data

        print(
            "OK integration:",
            {
                "swarm_id": swarm_id,
                "run_status": run_data["swarm"]["status"],
                "stop_reason": run_data["stop_reason"],
                "cycles": history_data["total_cycles"],
            },
        )


if __name__ == "__main__":
    main()
