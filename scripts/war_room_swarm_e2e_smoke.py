import json

import httpx


def main() -> None:
    base = "http://127.0.0.1:5163"
    with httpx.Client(timeout=15.0) as client:
        html = client.get(f"{base}/admin-dashboard.html")
        assert html.status_code == 200, html.text
        assert "Lanzar Enjambre" in html.text
        assert "Enjambres Recientes" in html.text

        create = client.post(
            f"{base}/swarm",
            json={
                "name": "Swarm UI War Room",
                "goal": "Coordinar canales whatsapp y shopify desde dashboard",
                "policy": "narrative-consensus",
                "agents": ["whatsapp", "shopify"],
            },
        )
        assert create.status_code == 200, create.text
        swarm_id = create.json()["id"]

        run = client.post(
            f"{base}/swarm/{swarm_id}/run",
            json={
                "objective": "Resolver incidente en ventas y soporte",
                "max_cycles": 3,
                "client_key": "war-room-ui",
            },
        )
        assert run.status_code == 200, run.text
        run_payload = run.json()

        recent = client.get(f"{base}/swarm", params={"limit": 10})
        assert recent.status_code == 200, recent.text
        recent_rows = recent.json()
        assert any(item["id"] == swarm_id for item in recent_rows), recent.text

        history = client.get(f"{base}/swarm/{swarm_id}/history")
        assert history.status_code == 200, history.text
        history_payload = history.json()
        assert history_payload["swarm"]["id"] == swarm_id, history.text

        print(
            "OK war room integration:",
            json.dumps(
                {
                    "swarm_id": swarm_id,
                    "decision": run_payload.get("decision"),
                    "stop_reason": run_payload.get("stop_reason"),
                    "cycles": history_payload.get("total_cycles"),
                },
                ensure_ascii=True,
            ),
        )


if __name__ == "__main__":
    main()
