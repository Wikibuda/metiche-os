from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session


def _build_dashboard_cards(status_payload: dict, events_by_channel: dict[str, list[dict]]) -> list[dict]:
    cards: list[dict] = []
    for channel_item in status_payload.get("channels", []):
        channel = str(channel_item.get("channel") or "").strip().lower()
        summary = channel_item.get("summary") or {}
        cards.append(
            {
                "channel": channel,
                "status": channel_item.get("status"),
                "healthy": bool(channel_item.get("healthy")),
                "send_messages": int(summary.get("send_messages") or 0),
                "events_count": len(events_by_channel.get(channel, [])),
            }
        )
    return cards


def main() -> None:
    db_path = Path(__file__).resolve().parent.parent / "data" / "db" / "channels_dashboard_smoke.db"
    if db_path.exists():
        db_path.unlink()

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["WHATSAPP_ALLOWED_NUMBERS"] = "+5210000000000,+5210000000001"
    os.environ["WHATSAPP_SANDBOX_MODE"] = "true"
    os.environ["TELEGRAM_ALLOWED_IDS"] = "123456789,987654321"
    os.environ["TELEGRAM_SANDBOX_MODE"] = "true"

    from app.core.db import engine
    from app.integrations.telegram_adapter import OutboundTelegramMessage, TelegramAdapter
    from app.integrations.whatsapp_adapter import OutboundWhatsAppMessage, WhatsAppAdapter
    from app.main import app

    with TestClient(app) as client:
        with Session(engine) as session:
            whatsapp = WhatsAppAdapter(session=session, api_client=client)
            telegram = TelegramAdapter(session=session, api_client=client)

            whatsapp.send_message(OutboundWhatsAppMessage(client_key="+5210000000001", text="Smoke dashboard WA"))
            telegram.send_message(OutboundTelegramMessage(client_key="123456789", text="Smoke dashboard TG"))

        html = client.get("/dashboard/swarm-console.html")
        assert html.status_code == 200, html.text
        assert "Estado de Canales" in html.text, "swarm-console debe incluir panel Estado de Canales"

        status = client.get("/dashboard/channels/status?event_preview_limit=5")
        assert status.status_code == 200, status.text
        status_payload = status.json()
        channels = status_payload.get("channels", [])
        assert len(channels) >= 2, status_payload

        by_name = {item["channel"]: item for item in channels}
        assert "whatsapp" in by_name and "telegram" in by_name, by_name
        assert by_name["whatsapp"]["status"] == "green", by_name["whatsapp"]
        assert by_name["telegram"]["status"] == "green", by_name["telegram"]

        wa_events_resp = client.get("/dashboard/channels/events?channel=whatsapp&limit=10")
        tg_events_resp = client.get("/dashboard/channels/events?channel=telegram&limit=10")
        assert wa_events_resp.status_code == 200, wa_events_resp.text
        assert tg_events_resp.status_code == 200, tg_events_resp.text
        wa_events = wa_events_resp.json().get("items", [])
        tg_events = tg_events_resp.json().get("items", [])
        assert any(str(item.get("event_type", "")).startswith("whatsapp_") for item in wa_events), wa_events
        assert any(str(item.get("event_type", "")).startswith("telegram_") for item in tg_events), tg_events

        cards = _build_dashboard_cards(
            status_payload,
            {
                "whatsapp": wa_events,
                "telegram": tg_events,
            },
        )
        assert any(card["channel"] == "whatsapp" and card["events_count"] > 0 for card in cards), cards
        assert any(card["channel"] == "telegram" and card["events_count"] > 0 for card in cards), cards

    print(
        "SMOKE_OK channels_dashboard",
        {
            "channels": [card["channel"] for card in cards],
            "statuses": {card["channel"]: card["status"] for card in cards},
            "events": {card["channel"]: card["events_count"] for card in cards},
        },
    )


if __name__ == "__main__":
    main()
