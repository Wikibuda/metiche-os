"""
FIFO Queue Service — 6 niveles de prioridad.

Orden de procesamiento (descendente):
  1. En_progreso  (tareas actualmente en ejecución)
  2. Blocking     (tareas que bloquean a otras)
  3. Urgent       (intervención humana o bug crítico)
  4. High         (lanzamiento enjambre, tareas de alto valor)
  5. Medium       (operaciones rutinarias)
  6. Low          (tareas de mantenimiento, backlog)

Mecanismo "encolar FIFO":
  Cuando un issue de Plane dice "encolar FIFO", el método enqueue_fifo()
  coloca la tarea al final de su nivel de prioridad (behind existing tasks
  of the same level) para respetar el orden de llegada.

Dependencias:
  - SQLAlchemy / sqlmodel Session
  - app.domain.tasks.models.{Task, QueueEntry, TaskEnqueueCreate}
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import Session, select

from app.domain.tasks.models import (
    QueueEntry,
    QueueEntryRead,
    Task,
    TaskEnqueueCreate,
)
from app.domain.tasks.service import create_task, derive_queue_bucket, normalize_priority

# ── 6 niveles de prioridad (orden descendente) ────────────────────────────
PRIORITY_LEVELS = ("en_progreso", "blocking", "urgent", "high", "medium", "low")
PRIORITY_ORDER = {level: idx for idx, level in enumerate(PRIORITY_LEVELS)}


def _validate_priority(priority: str) -> str:
    """Normaliza y valida una prioridad. Retorna el string normalizado o raise."""
    p = (priority or "medium").strip().lower().replace(" ", "_")
    if p not in PRIORITY_ORDER:
        raise ValueError(
            f"Prioridad inválida: '{priority}'. "
            f"Valores permitidos: {', '.join(PRIORITY_LEVELS)}"
        )
    return p


def _next_queue_position(session: Session, priority: str) -> int:
    """Calcula el próximo queue_position auto-increment para un nivel dado."""
    conn = session.connection()
    try:
        row = conn.execute(
            text(
                "SELECT COALESCE(MAX(queue_position), 0) + 1 AS next_pos "
                "FROM queueentry "
                "WHERE priority = :priority AND status = 'queued'"
            ),
            {"priority": priority},
        ).first()
        return row._mapping["next_pos"] if row else 1
    except Exception:
        return 1


# ── API pública ──────────────────────────────────────────────────────────


def enqueue(
    session: Session,
    task: Task | TaskEnqueueCreate,
    priority: str = "medium",
) -> QueueEntryRead:
    """
    Encola una tarea existente (Task) o crea una nueva desde un payload
    (TaskEnqueueCreate) y la encola con la prioridad indicada.

    Retorna la QueueEntry creada (como QueueEntryRead).
    """
    clean_priority = _validate_priority(priority)

    # Si recibimos un payload, creamos la Task primero
    if isinstance(task, TaskEnqueueCreate):
        task_create = create_task(session, task)
        task_obj = session.get(Task, task_create.id)
    else:
        task_obj = task

    if task_obj is None:
        raise ValueError("No se pudo resolver la tarea para encolar")

    # Actualizar el campo priority en Task
    task_obj.priority = clean_priority
    task_obj.queue_position = _next_queue_position(session, clean_priority)
    task_obj.status = "queued"
    task_obj.updated_at = datetime.utcnow()
    session.add(task_obj)
    session.flush()

    # Crear entrada en QueueEntry
    queue_entry = QueueEntry(
        task_id=task_obj.id,
        priority=clean_priority,
        queue_bucket=derive_queue_bucket(clean_priority),
        status="queued",
        enqueued_at=datetime.utcnow(),
    )
    session.add(queue_entry)
    session.commit()
    session.refresh(queue_entry)

    return QueueEntryRead.from_model(queue_entry)


def dequeue(session: Session) -> QueueEntry | None:
    """
    Extrae la siguiente tarea a procesar según orden de prioridad.

    Primero busca en En_progreso (ya en ejecución), luego Blocking,
    Urgent, High, Medium, Low. Dentro de cada nivel, ordena por
    queue_position ASC (FIFO).
    """
    for level in PRIORITY_LEVELS:
        entry = session.exec(
            select(QueueEntry)
            .where(
                QueueEntry.priority == level,
                QueueEntry.status == "queued",
            )
            .order_by(QueueEntry.enqueued_at.asc())
            .limit(1)
        ).first()
        if entry:
            entry.status = "processing"
            entry.started_at = datetime.utcnow()
            session.add(entry)

            # Actualizar Task asociada
            task = session.get(Task, entry.task_id)
            if task:
                task.status = "processing"
                task.updated_at = datetime.utcnow()
                session.add(task)

            session.commit()
            session.refresh(entry)
            return entry

    return None


def peek(session: Session, priority: str | None = None) -> list[QueueEntryRead]:
    """
    Mira la cola sin modificar nada.

    Si se pasa priority, filtra por ese nivel.
    Si no, muestra todos los niveles ordenados por prioridad + FIFO.
    """
    query = select(QueueEntry).where(QueueEntry.status == "queued")

    if priority:
        clean = _validate_priority(priority)
        query = query.where(QueueEntry.priority == clean)

    # Orden: por nivel de prioridad (según PRIORITY_ORDER), luego FIFO
    entries = session.exec(
        query.order_by(QueueEntry.enqueued_at.asc())
    ).all()

    # Orden externo usando PRIORITY_ORDER
    entries.sort(
        key=lambda e: (PRIORITY_ORDER.get(e.priority, 99), e.enqueued_at)
    )

    return [QueueEntryRead.from_model(e) for e in entries]


def get_queue_length(session: Session, priority: str | None = None) -> dict[str, int]:
    """
    Retorna un dict con la cantidad de elementos encolados por nivel.

    Ejemplo:
      {"en_progreso": 0, "blocking": 2, "urgent": 1, "high": 3, "medium": 5, "low": 8}
    """
    conn = session.connection()
    result = {level: 0 for level in PRIORITY_LEVELS}

    try:
        rows = conn.execute(
            text(
                "SELECT priority, COUNT(*) AS cnt "
                "FROM queueentry "
                "WHERE status = 'queued' "
                "GROUP BY priority"
            )
        ).fetchall()
        for row in rows:
            p = str(row._mapping["priority"]).lower()
            cnt = int(row._mapping["cnt"])
            if p in result:
                result[p] = cnt
    except Exception:
        pass

    if priority:
        clean = _validate_priority(priority)
        return {clean: result.get(clean, 0)}

    return result


def get_queue_full(session: Session) -> dict[str, Any]:
    """
    Retorna un dict completo con el estado de la cola:
      - lengths: dict por nivel
      - total: int
      - entries: list de QueueEntryRead
    """
    lengths = get_queue_length(session)
    entries = peek(session)
    total = sum(lengths.values())

    # Agrupar entries por nivel
    grouped: dict[str, list[dict[str, Any]]] = {level: [] for level in PRIORITY_LEVELS}
    for entry in entries:
        grouped[entry.priority].append({
            "id": entry.id,
            "task_id": entry.task_id,
            "priority": entry.priority,
            "queue_bucket": entry.queue_bucket,
            "status": entry.status,
            "enqueued_at": entry.enqueued_at.isoformat() if entry.enqueued_at else None,
        })

    # Cargar títulos de tareas
    task_ids = [e.task_id for e in entries]
    task_map: dict[str, str] = {}
    if task_ids:
        tasks = session.exec(select(Task).where(Task.id.in_(task_ids))).all()
        task_map = {t.id: t.title for t in tasks}

    for level in PRIORITY_LEVELS:
        for item in grouped[level]:
            item["title"] = task_map.get(item["task_id"], "Desconocido")

    return {
        "total": total,
        "lengths": lengths,
        "grouped": grouped,
    }


def enqueue_fifo(
    session: Session,
    payload: TaskEnqueueCreate,
    priority: str = "medium",
) -> QueueEntryRead:
    """
    Mecanismo "encolar FIFO" para Admin.

    Crea una Task y la coloca al final (FIFO) del nivel de prioridad indicado,
    detrás de todas las tareas existentes del mismo nivel.
    """
    return enqueue(session, payload, priority=priority)


def process_next(session: Session) -> dict[str, Any] | None:
    """
    Worker simple: extrae la siguiente tarea de la cola y la procesa.

    Retorna un dict con la info de la QueueEntry y la Task, o None si
    la cola está vacía.
    """
    entry = dequeue(session)
    if not entry:
        return None

    task = session.get(Task, entry.task_id)
    if not task:
        return None

    return {
        "queue_entry": QueueEntryRead.from_model(entry),
        "task": {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "queue_position": task.queue_position,
            "status": task.status,
            "task_type": task.task_type,
        },
    }


def can_enqueue(session: Session, priority: str) -> bool:
    """
    Verifica si se puede encolar una tarea con la prioridad dada.
    Siempre True a menos que la prioridad sea inválida.
    """
    try:
        _validate_priority(priority)
        return True
    except ValueError:
        return False
