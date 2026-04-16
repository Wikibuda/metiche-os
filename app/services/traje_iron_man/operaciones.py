from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import psycopg2
except Exception:  # pragma: no cover - optional dependency at runtime
    psycopg2 = None

from app.core.config import settings

logger = logging.getLogger(__name__)

OPERACIONES: dict[str, dict[str, str]] = {
    "archivar": {
        "nombre": "Archivado automatico mensual (>15 dias)",
        "analisis": """
            SELECT i.id, i.sequence_id, i.name
            FROM issues i
            JOIN states s ON i.state_id = s.id
            WHERE
                s.name = 'Done'
                AND i.completed_at < NOW() - INTERVAL '15 days'
                AND i.archived_at IS NULL
            ORDER BY i.completed_at ASC
            LIMIT 100
        """,
        "update": """
            UPDATE issues i
            SET
                archived_at = NOW(),
                updated_at = NOW()
            WHERE i.id IN ({ids_placeholder})
            RETURNING i.id, i.sequence_id, i.name
        """,
        "validacion": """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN archived_at IS NOT NULL THEN 1 ELSE 0 END) as archivados,
                SUM(CASE WHEN archived_at IS NULL THEN 1 ELSE 0 END) as no_archivados
            FROM issues i
            WHERE i.id IN ({ids_placeholder})
        """,
    },
    "limpiar-low": {
        "nombre": "Limpieza issues LOW obsoletos (>15 dias)",
        "analisis": """
            SELECT i.id, i.sequence_id, i.name
            FROM issues i
            JOIN states s ON i.state_id = s.id
            WHERE
                i.priority = 'low'
                AND s.name IN ('Backlog', 'Todo')
                AND i.archived_at IS NULL
                AND i.updated_at < NOW() - INTERVAL '15 days'
            ORDER BY i.updated_at ASC
            LIMIT 100
        """,
        "update": """
            UPDATE issues i
            SET
                state_id = (SELECT id FROM states WHERE name = 'Done' LIMIT 1),
                updated_at = NOW(),
                completed_at = NOW()
            WHERE i.id IN ({ids_placeholder})
            RETURNING i.id, i.sequence_id, i.name
        """,
        "validacion": """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN s.name = 'Done' THEN 1 ELSE 0 END) as completados,
                SUM(CASE WHEN s.name != 'Done' THEN 1 ELSE 0 END) as fallidos
            FROM issues i
            JOIN states s ON i.state_id = s.id
            WHERE i.id IN ({ids_placeholder})
        """,
    },
    "etiquetar": {
        "nombre": "Etiquetado automatico (auto-generated)",
        "analisis": """
            SELECT i.id, i.sequence_id, i.name
            FROM issues i
            WHERE
                i.archived_at >= NOW() - INTERVAL '7 days'
                AND NOT EXISTS (
                    SELECT 1 FROM issue_labels il
                    JOIN labels l ON il.label_id = l.id
                    WHERE il.issue_id = i.id AND l.name = 'auto-generated'
                )
            ORDER BY i.archived_at DESC
            LIMIT 100
        """,
        "update": """
            WITH label_info AS (
                SELECT id as label_id FROM labels WHERE name = 'auto-generated' LIMIT 1
            )
            INSERT INTO issue_labels (issue_id, label_id, created_at, updated_at)
            SELECT
                i.id,
                li.label_id,
                NOW(),
                NOW()
            FROM issues i
            CROSS JOIN label_info li
            WHERE i.id IN ({ids_placeholder})
                AND NOT EXISTS (
                    SELECT 1 FROM issue_labels il2
                    WHERE il2.issue_id = i.id AND il2.label_id = li.label_id
                )
            RETURNING issue_id, label_id
        """,
        "validacion": """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN il.issue_id IS NOT NULL THEN 1 ELSE 0 END) as etiquetados,
                SUM(CASE WHEN il.issue_id IS NULL THEN 1 ELSE 0 END) as no_etiquetados
            FROM issues i
            LEFT JOIN issue_labels il ON i.id = il.issue_id
                AND il.label_id = (SELECT id FROM labels WHERE name = 'auto-generated' LIMIT 1)
            WHERE i.id IN ({ids_placeholder})
        """,
    },
}

OPERACIONES_DISPONIBLES = sorted(OPERACIONES.keys())


def _state_path() -> Path:
    return Path(settings.traje_iron_man_state_path)


def _safe_load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        logger.exception("No se pudo leer estado de Traje Iron Man")
        return {}


def _save_state(payload: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _next_monthly_execution(now: datetime | None = None) -> datetime:
    base_now = now or datetime.now().astimezone()
    current_slot = base_now.replace(day=1, hour=3, minute=0, second=0, microsecond=0)
    if base_now < current_slot:
        return current_slot
    if current_slot.month == 12:
        return current_slot.replace(year=current_slot.year + 1, month=1)
    return current_slot.replace(month=current_slot.month + 1)


def _load_last_operation() -> dict[str, Any] | None:
    state = _safe_load_state()
    last = state.get("last_operation")
    return last if isinstance(last, dict) else None


def _store_last_operation(last_operation: dict[str, Any]) -> None:
    state = _safe_load_state()
    state["last_operation"] = last_operation
    state["next_execution"] = _next_monthly_execution().isoformat()
    _save_state(state)


def _resolve_telegram_target() -> str:
    explicit = str(settings.traje_iron_man_telegram_target or "").strip()
    if explicit:
        return explicit
    from_env = str(settings.telegram_user_id or settings.telegram_chat_id or "").strip()
    return from_env


def _notify_telegram(message: str) -> bool:
    target = _resolve_telegram_target()
    if not target:
        logger.info("Traje Iron Man: telegram target no configurado; se omite notificacion")
        return False
    command = [
        "openclaw",
        "message",
        "send",
        "--channel",
        "telegram",
        "--target",
        target,
        "--message",
        message,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except Exception:
        logger.exception("Error enviando notificacion Telegram")
        return False
    if result.returncode != 0:
        logger.warning("Fallo envio Telegram: %s", (result.stderr or result.stdout).strip())
        return False
    return True


def _direct_db_connection():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 no disponible")
    host = settings.plane_pg_host or "localhost"
    kwargs = dict(
        host=host,
        port=settings.plane_pg_port or 5432,
        user=settings.plane_pg_user,
        password=settings.plane_pg_password,
        dbname=settings.plane_pg_dbname,
        connect_timeout=max(1, int(settings.plane_timeout_seconds)),
    )
    try:
        return psycopg2.connect(**kwargs)
    except Exception:
        fallback_hosts: list[str] = []
        if host in {"localhost", "127.0.0.1"}:
            fallback_hosts.extend(["plane-db", "host.docker.internal"])
        elif host != "host.docker.internal":
            fallback_hosts.append("host.docker.internal")
        for fallback in fallback_hosts:
            try:
                kwargs["host"] = fallback
                return psycopg2.connect(**kwargs)
            except Exception:
                continue
        raise


def _quoted_ids(cursor: Any, issue_ids: list[str]) -> str:
    return ", ".join(cursor.mogrify("%s", (item,)).decode("utf-8") for item in issue_ids)


def _split_batches(items: list[str], batch_size: int) -> list[list[str]]:
    safe_size = max(1, batch_size)
    return [items[idx : idx + safe_size] for idx in range(0, len(items), safe_size)]


def run_traje_operation(
    *,
    operacion: str,
    lote: int = 20,
    dry_run: bool = False,
    trigger: str = "api",
) -> dict[str, Any]:
    if operacion not in OPERACIONES:
        raise ValueError(f"operacion_no_soportada:{operacion}")

    started_at = datetime.now(timezone.utc)
    config = OPERACIONES[operacion]
    safe_lote = max(1, min(int(lote), 200))
    metricas: dict[str, Any] = {
        "operacion": operacion,
        "nombre_operacion": config["nombre"],
        "trigger": trigger,
        "dry_run": dry_run,
        "lote": safe_lote,
        "started_at": started_at.isoformat(),
        "candidatos_identificados": 0,
        "lotes_procesados": 0,
        "issues_actualizados": 0,
        "errores": 0,
        "validacion": None,
    }

    processed_ids: list[str] = []
    try:
        with _direct_db_connection() as conn:
            conn.autocommit = False
            with conn.cursor() as cursor:
                cursor.execute(config["analisis"])
                rows = cursor.fetchall() or []
                candidate_ids = [str(row[0]) for row in rows if row and row[0] is not None]
                metricas["candidatos_identificados"] = len(candidate_ids)
                if dry_run or not candidate_ids:
                    conn.rollback()
                else:
                    for batch in _split_batches(candidate_ids, safe_lote):
                        try:
                            query_update = config["update"].replace("{ids_placeholder}", _quoted_ids(cursor, batch))
                            cursor.execute(query_update)
                            updated_rows = cursor.fetchall() or []
                            metricas["issues_actualizados"] += len(updated_rows)
                            metricas["lotes_procesados"] += 1
                            processed_ids.extend(batch)
                            conn.commit()
                        except Exception:
                            metricas["errores"] += 1
                            conn.rollback()
                            logger.exception("Lote con error en operacion %s", operacion)

                    if processed_ids:
                        validation_sql = config["validacion"].replace(
                            "{ids_placeholder}",
                            _quoted_ids(cursor, processed_ids),
                        )
                        cursor.execute(validation_sql)
                        validation_row = cursor.fetchone()
                        metricas["validacion"] = str(validation_row[0]) if validation_row else None
        finished_at = datetime.now(timezone.utc)
        metricas["finished_at"] = finished_at.isoformat()
        metricas["duracion_segundos"] = (finished_at - started_at).total_seconds()
        metricas["ok"] = metricas["errores"] == 0
        message = (
            f"Traje Iron Man | {operacion} | ok={metricas['ok']} | "
            f"candidatos={metricas['candidatos_identificados']} | "
            f"actualizados={metricas['issues_actualizados']} | "
            f"errores={metricas['errores']} | dry_run={dry_run}"
        )
        metricas["telegram_notified"] = _notify_telegram(message)
        _store_last_operation(metricas)
        return metricas
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        metricas["finished_at"] = finished_at.isoformat()
        metricas["duracion_segundos"] = (finished_at - started_at).total_seconds()
        metricas["ok"] = False
        metricas["error"] = str(exc)
        metricas["telegram_notified"] = _notify_telegram(
            f"Traje Iron Man | {operacion} | ok=false | error={str(exc)[:180]}"
        )
        _store_last_operation(metricas)
        raise


def get_traje_status() -> dict[str, Any]:
    return {
        "last_operation": _load_last_operation(),
        "next_execution": _next_monthly_execution().isoformat(),
        "schedule": {
            "frequency": "monthly",
            "day_of_month": 1,
            "hour_local": 3,
            "description": "Primer dia del mes a las 03:00",
        },
    }


def should_run_monthly_archive(now: datetime, last_operation: dict[str, Any] | None) -> bool:
    monthly_slot = now.replace(day=1, hour=3, minute=0, second=0, microsecond=0)
    if now < monthly_slot:
        return False
    if now.day != 1:
        return False
    if not last_operation:
        return True
    if str(last_operation.get("operacion")) != "archivar":
        return True
    started_at_raw = str(last_operation.get("started_at") or "")
    if not started_at_raw:
        return True
    try:
        last_started = datetime.fromisoformat(started_at_raw.replace("Z", "+00:00"))
    except Exception:
        return True
    # Avoid duplicate execution in the same monthly slot.
    return last_started < monthly_slot


def monthly_due_window(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=3, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)
