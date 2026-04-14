from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _setup_environment() -> Path:
    db_path = Path(__file__).resolve().parent.parent / "data" / "db" / "operational_validation.db"
    if db_path.exists():
        db_path.unlink()

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["WHATSAPP_ALLOWED_NUMBERS"] = "+5210000000000,+5210000000001,+5218142982923"
    os.environ["WHATSAPP_SANDBOX_MODE"] = "true"
    os.environ["TELEGRAM_ALLOWED_IDS"] = "123456789,987654321"
    os.environ["TELEGRAM_SANDBOX_MODE"] = "true"
    os.environ["OPENCLAW_GATEWAY_URL"] = os.environ.get("OPENCLAW_GATEWAY_URL", "http://host.docker.internal:18797")
    return db_path


def _event_count(session: Session, *, task_id: str, event_type: str) -> int:
    value = session.connection().execute(
        text(
            """
            SELECT COUNT(1)
            FROM task_events
            WHERE task_id = :task_id
              AND event_type = :event_type
            """
        ),
        {"task_id": task_id, "event_type": event_type},
    ).scalar_one()
    return int(value or 0)


def _event_exists_like(session: Session, *, event_type: str, payload_contains: str) -> bool:
    row = session.connection().execute(
        text(
            """
            SELECT id
            FROM task_events
            WHERE event_type = :event_type
              AND payload_json LIKE :payload_like
            LIMIT 1
            """
        ),
        {"event_type": event_type, "payload_like": f"%{payload_contains}%"},
    ).first()
    return row is not None


def test_inbound(client: TestClient, session: Session) -> CheckResult:
    phone = "+5210000000000"
    text_message = "Hola Metiche, prueba inbound operacional."
    response = client.post(
        "/webhooks/openclaw/whatsapp",
        json={
            "channel": "whatsapp",
            "from": phone,
            "content": text_message,
            "metadata": {"source": "operational_validation"},
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    trace_task_id = payload["trace_task_id"]

    count = _event_count(session, task_id=trace_task_id, event_type="whatsapp_message_received")
    assert count >= 1, {"trace_task_id": trace_task_id, "event_count": count}

    memory = client.get(f"/channel-memory/{phone}?channel=whatsapp")
    assert memory.status_code == 200, memory.text
    context = (memory.json() or {}).get("context") or {}
    assert context.get("last_user_message") == text_message, context

    return CheckResult(
        name="Prueba de Inbound",
        passed=True,
        detail=f"Evento whatsapp_message_received registrado y memoria actualizada (task_id={trace_task_id}).",
    )


def test_outbound(client: TestClient, session: Session) -> CheckResult:
    from app.integrations.whatsapp_adapter import OutboundWhatsAppMessage, WhatsAppAdapter

    adapter = WhatsAppAdapter(session=session, api_client=client)
    message = "Mensaje outbound simulado para validación v1.0.0"
    result = adapter.send_message(OutboundWhatsAppMessage(client_key="+5210000000000", text=message))
    assert bool(result.get("success")) is True, result
    trace_task_id = str(result.get("trace_task_id") or "")
    assert trace_task_id, result

    count = _event_count(session, task_id=trace_task_id, event_type="whatsapp_send_message")
    assert count >= 1, {"trace_task_id": trace_task_id, "event_count": count}

    return CheckResult(
        name="Prueba de Outbound",
        passed=True,
        detail=f"Se creó whatsapp_send_message en modo simulado (task_id={trace_task_id}).",
    )


def test_memory(client: TestClient, session: Session) -> CheckResult:
    from app.integrations.whatsapp_adapter import IncomingWhatsAppMessage, WhatsAppAdapter

    phone = "+5210000000001"
    adapter = WhatsAppAdapter(session=session, api_client=client)
    turn_1 = "Hola, soy Ana. Pedido 12345."
    turn_2 = "¿Me confirmas estatus del pedido 12345?"

    first = adapter.handle_incoming_message(IncomingWhatsAppMessage(phone_number=phone, text=turn_1))
    second = adapter.handle_incoming_message(IncomingWhatsAppMessage(phone_number=phone, text=turn_2))

    assert first.updated_context.get("last_user_message") == turn_1, first.updated_context
    assert second.loaded_context.get("last_user_message") == turn_1, second.loaded_context
    assert second.updated_context.get("last_user_message") == turn_2, second.updated_context
    assert "pedido 12345" in second.prompt.lower(), second.prompt

    memory = client.get(f"/channel-memory/{phone}?channel=whatsapp")
    assert memory.status_code == 200, memory.text
    context = (memory.json() or {}).get("context") or {}
    assert context.get("last_user_message") == turn_2, context

    return CheckResult(
        name="Prueba de Memoria",
        passed=True,
        detail="La segunda interacción recuperó contexto previo y persistió el nuevo turno correctamente.",
    )


def test_dashboard(client: TestClient, _session: Session) -> CheckResult:
    status_resp = client.get("/dashboard/channels/status?event_preview_limit=5")
    assert status_resp.status_code == 200, status_resp.text
    status_payload = status_resp.json()
    channels = status_payload.get("channels")
    assert isinstance(channels, list), status_payload
    by_channel = {str(item.get("channel")): item for item in channels}
    assert "whatsapp" in by_channel, status_payload

    events_resp = client.get("/dashboard/channels/events?channel=whatsapp&limit=10")
    assert events_resp.status_code == 200, events_resp.text
    events_payload = events_resp.json()
    items = events_payload.get("items")
    assert isinstance(items, list), events_payload
    assert any(str(item.get("event_type") or "").startswith("whatsapp_") for item in items), items

    return CheckResult(
        name="Prueba de Dashboard",
        passed=True,
        detail="Endpoints /dashboard/channels/status y /dashboard/channels/events responden correctamente.",
    )


def test_resilience(app, session: Session) -> CheckResult:
    marker = "falla_temporal_operational_validation"
    with TestClient(app, raise_server_exceptions=False) as resilient_client:
        with patch("app.api.routes_webhooks.WhatsAppAdapter.handle_incoming_message", side_effect=RuntimeError("temporary webhook failure")):
            response = resilient_client.post(
                "/webhooks/openclaw/whatsapp",
                json={
                    "channel": "whatsapp",
                    "from": "+5210000000000",
                    "content": marker,
                },
            )
    assert response.status_code >= 500, response.text

    received_logged = _event_exists_like(
        session,
        event_type="whatsapp_message_received",
        payload_contains=marker,
    )
    assert not received_logged, "No debe registrarse whatsapp_message_received cuando el adapter falla antes de emitir evento."

    return CheckResult(
        name="Prueba de Resiliencia (mock)",
        passed=True,
        detail="Falla temporal simulada en webhook detectada; no se registró evento inconsistente.",
    )


def run_check(name: str, fn) -> CheckResult:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name=name, passed=False, detail=f"{type(exc).__name__}: {exc}")


def main() -> int:
    db_path = _setup_environment()
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from app.core.db import engine
    from app.main import app

    results: list[CheckResult] = []

    with TestClient(app) as client:
        with Session(engine) as session:
            results.append(run_check("Prueba de Inbound", lambda: test_inbound(client, session)))
            results.append(run_check("Prueba de Outbound", lambda: test_outbound(client, session)))
            results.append(run_check("Prueba de Memoria", lambda: test_memory(client, session)))
            results.append(run_check("Prueba de Dashboard", lambda: test_dashboard(client, session)))
            results.append(run_check("Prueba de Resiliencia (mock)", lambda: test_resilience(app, session)))

    passed_count = sum(1 for item in results if item.passed)
    total = len(results)

    print("\n=== VALIDACION OPERACIONAL METICHE v1.0.0 ===")
    print(f"DB temporal: {db_path}")
    print("--------------------------------------------")
    for item in results:
        status = "✅ PASÓ" if item.passed else "❌ FALLÓ"
        print(f"{status} | {item.name}")
        print(f"    {item.detail}")
    print("--------------------------------------------")
    global_ok = passed_count == total
    print(f"VEREDICTO GLOBAL: {'✅ LISTO PARA v1.0.0' if global_ok else '❌ NO LISTO PARA v1.0.0'} ({passed_count}/{total})")
    return 0 if global_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
