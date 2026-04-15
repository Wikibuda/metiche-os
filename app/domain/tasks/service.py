import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import Session, select

from app.core.config import settings
from app.domain.validators import DashboardValidator, DeepseekValidator, ShopifyValidator, TelegramValidator, ValidationResult, WhatsAppValidator
from app.domain.narrative.models import NarrativeEntryCreate
from app.domain.narrative.service import create_narrative_entry
from app.domain.tasks.models import Decision, DecisionRead, EngineDispatch, EngineDispatchRead, EscalationRead, Execution, ExecutionRead, OperationalOverviewRead, QueueEntry, QueueEntryRead, RouteResolution, RouteResolutionRead, Task, TaskCreate, TaskEnqueueCreate, TaskFlowRead, TaskQueueProcessRead, TaskRead, TaskRunCreate, Validation, ValidationRead
from app.services.plane_bridge_service import sync_task_status_to_plane


def create_task(session: Session, payload: TaskCreate) -> TaskRead:
    task = Task(
        title=payload.title,
        description=payload.description,
        execution_mode=payload.execution_mode,
        task_type=payload.task_type,
        status="queued" if payload.execution_mode == "queued" else "deciding",
        updated_at=datetime.utcnow(),
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return TaskRead.from_model(task)


def list_tasks(session: Session) -> list[TaskRead]:
    items = session.exec(select(Task).order_by(Task.created_at.desc())).all()
    return [TaskRead.from_model(item) for item in items]


def run_task_flow(session: Session, payload: TaskRunCreate) -> TaskFlowRead:
    now = datetime.utcnow()
    task = Task(
        title=payload.title,
        description=payload.description,
        execution_mode=payload.execution_mode,
        task_type=payload.task_type,
        status="deciding",
        updated_at=now,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    chosen_path, rationale = decide_task_path(payload)
    decision = Decision(
        task_id=task.id,
        decision_type="routing",
        chosen_path=chosen_path,
        rationale=rationale,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)

    execution = Execution(
        task_id=task.id,
        decision_id=decision.id,
        actor_code="metiche",
        status="completed",
        summary=build_execution_summary(task, decision),
        started_at=now,
        completed_at=datetime.utcnow(),
    )
    session.add(execution)
    session.commit()
    session.refresh(execution)

    validation_result = _validate_execution(session, task, execution)
    execution.status = "completed" if validation_result["status"] == "passed" else "failed"
    session.add(execution)
    session.commit()
    session.refresh(execution)
    validation = Validation(
        task_id=task.id,
        execution_id=execution.id,
        validator_code="metiche",
        status=validation_result["status"],
        notes=validation_result["notes"],
    )
    session.add(validation)
    task.status = "validated" if validation_result["status"] == "passed" else "failed"
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(validation)
    session.refresh(task)
    _emit_task_event(
        session,
        task=task,
        execution=execution,
        decision=decision,
        validation=validation,
        retry_scheduled=False,
    )

    narrative = create_narrative_entry(
        session,
        NarrativeEntryCreate(
            title=f"Metiche movió la misión: {task.title}",
            body=build_chronicle(task, decision, execution, validation),
            narrative_type="chronicle",
            wonder_level=4 if payload.execution_mode == "immediate" else 3,
            narrator_code="metiche",
        ),
    )

    return TaskFlowRead(
        task=TaskRead.from_model(task),
        decision=DecisionRead.from_model(decision),
        execution=ExecutionRead.from_model(execution),
        validation=ValidationRead.from_model(validation),
        narrative=narrative,
    )


def get_task_flow(session: Session, task_id: str) -> TaskFlowRead | None:
    task = session.get(Task, task_id)
    if not task:
        return None

    decision = session.exec(select(Decision).where(Decision.task_id == task_id).order_by(Decision.created_at.desc())).first()
    execution = session.exec(select(Execution).where(Execution.task_id == task_id).order_by(Execution.started_at.desc())).first()
    validation = session.exec(select(Validation).where(Validation.task_id == task_id).order_by(Validation.created_at.desc())).first()

    if not decision or not execution or not validation:
        return None

    return TaskFlowRead(
        task=TaskRead.from_model(task),
        decision=DecisionRead.from_model(decision),
        execution=ExecutionRead.from_model(execution),
        validation=ValidationRead.from_model(validation),
        narrative=None,
    )


def validate_task_by_id(session: Session, task_id: str) -> dict[str, Any] | None:
    task = session.get(Task, task_id)
    if not task:
        return None
    decision = session.exec(select(Decision).where(Decision.task_id == task_id).order_by(Decision.created_at.desc())).first()
    execution = session.exec(select(Execution).where(Execution.task_id == task_id).order_by(Execution.started_at.desc())).first()
    if not decision or not execution:
        return {"task_id": task_id, "status": "error", "message": "No existe decision/ejecucion para validar."}

    validation_result = _validate_execution(session, task, execution)
    validation = Validation(
        task_id=task.id,
        execution_id=execution.id,
        validator_code="metiche-manual",
        status=validation_result["status"],
        notes=validation_result["notes"],
    )
    session.add(validation)
    task.status = "validated" if validation_result["status"] == "passed" else "failed"
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(validation)
    session.refresh(task)
    _emit_task_event(
        session,
        task=task,
        execution=execution,
        decision=decision,
        validation=validation,
        retry_scheduled=False,
    )
    return {
        "task_id": task_id,
        "status": validation.status,
        "task_status": task.status,
        "notes": validation.notes,
        "results": [
            {
                "channel": item.channel,
                "passed": item.passed,
                "critical": item.critical,
                "detail": item.detail,
                "metadata": item.metadata or {},
            }
            for item in validation_result["results"]
        ],
    }


def decide_task_path(payload: TaskRunCreate) -> tuple[str, str]:
    if payload.task_type == "whatsapp":
        return "reasoner_whatsapp", "WhatsApp siempre se enruta por el Reasoner."
    if payload.execution_mode == "immediate":
        return "metiche_direct", "Gus pidió ejecución inmediata, así que Metiche abre paso directo."
    if payload.task_type in {"analysis", "planning"}:
        return "metiche_planning", "La tarea requiere criterio directo antes de lanzar enjambres."
    return "swarm_lane", "La tarea entra al carril operativo para ejecución automatizable."


def build_execution_summary(task: Task, decision: Decision) -> str:
    return f"Metiche ejecutó '{task.title}' por la ruta {decision.chosen_path}."


def build_validation_notes(task: Task, payload: TaskRunCreate) -> str:
    return f"Validación local completada para '{task.title}' con modo {payload.execution_mode}."


def build_chronicle(task: Task, decision: Decision, execution: Execution, validation: Validation) -> str:
    return (
        f"Metiche recibió la misión '{task.title}' y la empujó por la ruta {decision.chosen_path}. "
        f"La ejecución cerró con estado {execution.status} y la validación quedó en {validation.status}. "
        "Jefe, el laboratorio ya dejó memoria viva de este movimiento."
    )


PRIORITY_ORDER = {
    "blocking": 0,
    "urgent": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
}


def enqueue_task(session: Session, payload: TaskEnqueueCreate) -> QueueEntryRead:
    now = datetime.utcnow()
    priority = normalize_priority(payload.priority)
    task = Task(
        title=payload.title,
        description=payload.description,
        execution_mode="queued",
        task_type=payload.task_type,
        status="queued",
        updated_at=now,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    queue_entry = QueueEntry(
        task_id=task.id,
        priority=priority,
        queue_bucket=derive_queue_bucket(priority),
        status="queued",
        enqueued_at=now,
    )
    session.add(queue_entry)
    session.commit()
    session.refresh(queue_entry)
    return QueueEntryRead.from_model(queue_entry)


def list_queue_entries(session: Session) -> list[QueueEntryRead]:
    rows = session.exec(select(QueueEntry).where(QueueEntry.status == "queued")).all()
    ordered = sorted(rows, key=queue_sort_key)
    return [QueueEntryRead.from_model(item) for item in ordered]


def process_next_task(session: Session) -> TaskQueueProcessRead | None:
    rows = session.exec(select(QueueEntry).where(QueueEntry.status == "queued")).all()
    if not rows:
        return None

    queue_entry = sorted(rows, key=queue_sort_key)[0]
    task = session.get(Task, queue_entry.task_id)
    if not task:
        queue_entry.status = "missing_task"
        queue_entry.completed_at = datetime.utcnow()
        session.add(queue_entry)
        session.commit()
        return None

    queue_entry.status = "processing"
    queue_entry.started_at = datetime.utcnow()
    task.status = "deciding"
    task.updated_at = datetime.utcnow()
    session.add(queue_entry)
    session.add(task)
    session.commit()

    flow = execute_task_entity(session, task)

    queue_entry.status = "completed"
    queue_entry.completed_at = datetime.utcnow()
    session.add(queue_entry)
    session.commit()
    session.refresh(queue_entry)
    return TaskQueueProcessRead(queue_entry=QueueEntryRead.from_model(queue_entry), flow=flow)


def execute_task_entity(session: Session, task: Task) -> TaskFlowRead:
    payload = TaskRunCreate(
        title=task.title,
        description=task.description,
        execution_mode=task.execution_mode,
        task_type=task.task_type,
    )
    chosen_path, rationale = decide_task_path(payload)
    route_resolution = RouteResolution(
        task_id=task.id,
        channel=infer_channel(task.task_type),
        route_family=chosen_path,
        target_engine=determine_target_engine(chosen_path),
        target_actor="metiche",
        matched_rule_code=determine_rule_code(payload),
        rationale=rationale,
    )
    session.add(route_resolution)
    session.commit()
    session.refresh(route_resolution)

    decision = Decision(
        task_id=task.id,
        decision_type="routing",
        chosen_path=chosen_path,
        rationale=rationale,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)

    execution = Execution(
        task_id=task.id,
        decision_id=decision.id,
        actor_code="metiche",
        status="completed",
        summary=build_execution_summary(task, decision),
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    session.add(execution)
    session.commit()
    session.refresh(execution)

    validation = Validation(
        task_id=task.id,
        execution_id=execution.id,
        validator_code="metiche",
        status="passed",
        notes=build_validation_notes(task, payload),
    )
    session.add(validation)
    task.status = "validated"
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(validation)
    session.refresh(task)

    narrative = create_narrative_entry(
        session,
        NarrativeEntryCreate(
            title=f"Metiche movió la misión: {task.title}",
            body=build_chronicle(task, decision, execution, validation),
            narrative_type="chronicle",
            wonder_level=4 if task.execution_mode == "immediate" else 3,
            narrator_code="metiche",
        ),
    )
    return TaskFlowRead(
        task=TaskRead.from_model(task),
        decision=DecisionRead.from_model(decision),
        execution=ExecutionRead.from_model(execution),
        validation=ValidationRead.from_model(validation),
        narrative=narrative,
    )


def normalize_priority(priority: str) -> str:
    value = priority.lower().strip()
    return value if value in PRIORITY_ORDER else "medium"


def queue_sort_key(queue_entry: QueueEntry) -> tuple[int, datetime]:
    return (PRIORITY_ORDER.get(queue_entry.priority, PRIORITY_ORDER["medium"]), queue_entry.enqueued_at)


def get_task_route_resolution(session: Session, task_id: str) -> RouteResolutionRead | None:
    row = session.exec(select(RouteResolution).where(RouteResolution.task_id == task_id).order_by(RouteResolution.created_at.desc())).first()
    if not row:
        return None
    return RouteResolutionRead.from_model(row)


def derive_queue_bucket(priority: str) -> str:
    mapping = {
        "blocking": "monticulo_bloqueantes",
        "urgent": "monticulo_urgentes",
        "high": "monticulo_high",
        "medium": "monticulo_medium",
        "low": "monticulo_low",
    }
    return mapping.get(priority, "monticulo_medium")


def infer_channel(task_type: str) -> str:
    if task_type == "whatsapp":
        return "whatsapp"
    if task_type == "telegram":
        return "telegram"
    if task_type == "webchat":
        return "webchat"
    return "internal"


def determine_target_engine(chosen_path: str) -> str:
    if chosen_path == "reasoner_whatsapp":
        return "deepseek_reasoner"
    if chosen_path in {"metiche_planning", "metiche_direct"}:
        return "metiche_direct"
    return "swarm_runtime"


def determine_rule_code(payload: TaskRunCreate) -> str:
    if payload.task_type == "whatsapp":
        return "rule_03_whatsapp_reasoner"
    if payload.execution_mode == "immediate":
        return "rule_00_immediate_override"
    if payload.task_type in {"analysis", "planning"}:
        return "rule_planning_direct"
    return "rule_11_fifo_default"


MAX_VALIDATION_RETRIES = 2


def _validator_registry() -> dict[str, object]:
    return {
        "telegram": TelegramValidator(),
        "whatsapp": WhatsAppValidator(),
        "dashboard": DashboardValidator(),
        "shopify": ShopifyValidator(),
        "deepseek": DeepseekValidator(),
    }


def _resolve_required_channels(task: Task) -> list[str]:
    channels: list[str] = []
    task_type_map = {
        "telegram": ["telegram"],
        "whatsapp": ["whatsapp"],
        "dashboard": ["dashboard"],
        "shopify": ["shopify"],
        "analysis": ["deepseek"],
    }
    channels.extend(task_type_map.get(task.task_type, []))

    description = (task.description or "").lower()
    if "[channels=" in description:
        marker = description.split("[channels=", 1)[1].split("]", 1)[0]
        channels.extend([item.strip() for item in marker.split(",") if item.strip()])
    if settings.validation_required_channels.strip():
        channels.extend([item.strip() for item in settings.validation_required_channels.split(",") if item.strip()])
    deduped: list[str] = []
    for channel in channels:
        if channel not in deduped:
            deduped.append(channel)
    return deduped


def _validation_wonder_level(result: ValidationResult) -> int:
    if not result.passed and result.critical:
        return 5
    if result.passed:
        return 4
    return 3


def _emit_validation_attempt_event(
    session: Session,
    task: Task,
    execution: Execution,
    result: ValidationResult,
) -> None:
    payload = {
        "channel": result.channel,
        "passed": result.passed,
        "critical": result.critical,
        "detail": result.detail,
        "metadata": result.metadata or {},
    }
    importance_level = "critical" if (not result.passed and result.critical) else ("high" if not result.passed else "low")
    try:
        conn = session.connection()
        conn.execute(
            text(
                """
                INSERT INTO task_events (
                    id, task_id, execution_id, event_type, event_summary, importance_level,
                    wonder_level, payload_json, occurred_at, created_at
                ) VALUES (
                    :id, :task_id, :execution_id, :event_type, :event_summary, :importance_level,
                    :wonder_level, :payload_json, :occurred_at, :created_at
                )
                """
            ),
            {
                "id": str(uuid4()),
                "task_id": task.id,
                "execution_id": execution.id,
                "event_type": "validation_attempt",
                "event_summary": f"Canal {result.channel}: {'passed' if result.passed else 'failed'}",
                "importance_level": importance_level,
                "wonder_level": _validation_wonder_level(result),
                "payload_json": json.dumps(payload, ensure_ascii=False),
                "occurred_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
            },
        )
        session.commit()
    except Exception:
        session.rollback()


def _validate_execution(session: Session, task: Task, execution: Execution) -> dict[str, Any]:
    required_channels = _resolve_required_channels(task)
    if not required_channels:
        return {"status": "passed", "notes": "Sin validadores requeridos para esta tarea.", "results": []}

    registry = _validator_registry()
    results: list[ValidationResult] = []
    for channel in required_channels:
        validator = registry.get(channel)
        if validator is None:
            result = ValidationResult(channel=channel, passed=False, detail=f"No existe validador para canal '{channel}'", critical=False)
        else:
            result = validator.validate(task.title, task.description or "")
        results.append(result)
        _emit_validation_attempt_event(session, task=task, execution=execution, result=result)

    all_passed = all(item.passed for item in results)
    notes = "; ".join([f"{item.channel}={'ok' if item.passed else 'fail'} ({item.detail})" for item in results])
    return {"status": "passed" if all_passed else "failed", "notes": notes, "results": results}


def _resolve_validation_plan(session: Session, task: Task, validation_result: dict[str, Any]) -> str:
    if validation_result["status"] == "passed":
        return "passed"
    failed_rows = session.exec(select(Validation).where(Validation.task_id == task.id, Validation.status == "failed")).all()
    failed_count = len(failed_rows)
    has_critical_failure = any((not item.passed and item.critical) for item in validation_result.get("results", []))
    if has_critical_failure:
        return "failed"
    return "retry" if failed_count < MAX_VALIDATION_RETRIES - 1 else "failed"


def _emit_task_event(
    session: Session,
    task: Task,
    execution: Execution,
    decision: Decision,
    validation: Validation,
    retry_scheduled: bool,
) -> None:
    retry_count = len(
        session.exec(select(Validation).where(Validation.task_id == task.id, Validation.status == "failed")).all()
    )
    importance_level = "high" if retry_scheduled or validation.status == "failed" or retry_count > 0 else "low"
    wonder_level = 5 if importance_level == "high" else 2
    if retry_scheduled:
        event_type = "task_execution_retry"
    elif validation.status == "failed":
        event_type = "task_execution_failed"
    else:
        event_type = "task_execution_completed"
    event_summary = (
        f"Mision '{task.title}' finalizo con validacion={validation.status}, "
        f"ruta={decision.chosen_path}, retries={retry_count}."
    )
    payload = {
        "task_title": task.title,
        "task_type": task.task_type,
        "execution_mode": task.execution_mode,
        "decision_path": decision.chosen_path,
        "execution_status": execution.status,
        "validation_status": validation.status,
        "retry_count": retry_count,
        "retry_scheduled": retry_scheduled,
    }
    conn = session.connection()
    try:
        conn.execute(
            text(
                """
                INSERT INTO task_events (
                    id, task_id, execution_id, event_type, event_summary, importance_level,
                    wonder_level, payload_json, occurred_at, created_at
                ) VALUES (
                    :id, :task_id, :execution_id, :event_type, :event_summary, :importance_level,
                    :wonder_level, :payload_json, :occurred_at, :created_at
                )
                """
            ),
            {
                "id": str(uuid4()),
                "task_id": task.id,
                "execution_id": execution.id,
                "event_type": event_type,
                "event_summary": event_summary,
                "importance_level": importance_level,
                "wonder_level": wonder_level,
                "payload_json": json.dumps(payload, ensure_ascii=False),
                "occurred_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
            },
        )
        session.commit()
    except Exception:
        session.rollback()

def process_next_task(session: Session) -> TaskQueueProcessRead | None:
    rows = session.exec(select(QueueEntry).where(QueueEntry.status == "queued")).all()
    if not rows:
        return None

    queue_entry = sorted(rows, key=queue_sort_key)[0]
    task = session.get(Task, queue_entry.task_id)
    if not task:
        queue_entry.status = "missing_task"
        queue_entry.completed_at = datetime.utcnow()
        session.add(queue_entry)
        session.commit()
        return None

    queue_entry.status = "processing"
    queue_entry.started_at = datetime.utcnow()
    task.status = "deciding"
    task.updated_at = datetime.utcnow()
    session.add(queue_entry)
    session.add(task)
    session.commit()

    flow, retry_scheduled, message = execute_task_entity(session, task)

    if retry_scheduled:
        queue_entry.status = "queued"
        queue_entry.completed_at = None
    else:
        queue_entry.status = "completed" if flow.validation.status == "passed" else "failed"
        queue_entry.completed_at = datetime.utcnow()
    session.add(queue_entry)
    session.commit()
    session.refresh(queue_entry)
    return TaskQueueProcessRead(queue_entry=QueueEntryRead.from_model(queue_entry), flow=flow, retry_scheduled=retry_scheduled, message=message)


def execute_task_entity(session: Session, task: Task) -> tuple[TaskFlowRead, bool, str | None]:
    payload = TaskRunCreate(
        title=task.title,
        description=task.description,
        execution_mode=task.execution_mode,
        task_type=task.task_type,
    )
    chosen_path, rationale = decide_task_path(payload)
    route_resolution = RouteResolution(
        task_id=task.id,
        channel=infer_channel(task.task_type),
        route_family=chosen_path,
        target_engine=determine_target_engine(chosen_path),
        target_actor="metiche",
        matched_rule_code=determine_rule_code(payload),
        rationale=rationale,
    )
    session.add(route_resolution)
    session.commit()
    session.refresh(route_resolution)

    primary_engine, fallback_engine = determine_engine_plan(chosen_path)
    fallback_used = should_force_fallback(task, primary_engine) and fallback_engine is not None
    final_engine = fallback_engine if fallback_used and fallback_engine else primary_engine
    dispatch_status = "fallback_completed" if fallback_used else "completed"
    engine_dispatch = EngineDispatch(
        task_id=task.id,
        route_resolution_id=route_resolution.id,
        primary_engine=primary_engine,
        fallback_engine=fallback_engine,
        final_engine=final_engine,
        fallback_used=fallback_used,
        dispatch_status=dispatch_status,
    )
    session.add(engine_dispatch)
    session.commit()

    decision = Decision(
        task_id=task.id,
        decision_type="routing",
        chosen_path=chosen_path,
        rationale=rationale,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)

    execution = Execution(
        task_id=task.id,
        decision_id=decision.id,
        actor_code=final_engine,
        status="completed",
        summary=build_execution_summary(task, decision) + f" Motor final: {final_engine}.",
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    session.add(execution)
    session.commit()
    session.refresh(execution)

    validation_result = _validate_execution(session, task, execution)
    validation_plan = _resolve_validation_plan(session, task, validation_result)
    execution.status = "retry_required" if validation_plan == "retry" else ("failed" if validation_plan == "failed" else "completed")
    session.add(execution)
    session.commit()
    session.refresh(execution)

    validation_status = "passed" if validation_plan == "passed" else "failed"
    validation = Validation(
        task_id=task.id,
        execution_id=execution.id,
        validator_code="metiche",
        status=validation_status,
        notes=validation_result["notes"],
    )
    session.add(validation)

    if validation_plan == "retry":
        task.status = "retrying"
    elif validation_plan == "failed":
        task.status = "failed"
    else:
        task.status = "validated"
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(validation)
    session.refresh(task)

    failed_channels = [
        item.channel
        for item in validation_result.get("results", [])
        if isinstance(item, ValidationResult) and not item.passed
    ]
    if validation_plan in {"failed", "passed"} and settings.plane_sync_enabled:
        try:
            sync_task_status_to_plane(
                session,
                task=task,
                failed_channels=failed_channels if validation_plan == "failed" else [],
            )
        except Exception:
            session.rollback()

    _emit_task_event(
        session,
        task=task,
        execution=execution,
        decision=decision,
        validation=validation,
        retry_scheduled=(validation_plan == "retry"),
    )

    narrative = None
    if validation_plan != "retry":
        narrative = create_narrative_entry(
            session,
            NarrativeEntryCreate(
                title=f"Metiche movió la misión: {task.title}",
                body=build_chronicle(task, decision, execution, validation),
                narrative_type="chronicle",
                wonder_level=4 if task.execution_mode == "immediate" else 3,
                narrator_code="metiche",
            ),
        )

    flow = TaskFlowRead(
        task=TaskRead.from_model(task),
        decision=DecisionRead.from_model(decision),
        execution=ExecutionRead.from_model(execution),
        validation=ValidationRead.from_model(validation),
        narrative=narrative,
    )
    if validation_plan == "retry":
        return flow, True, "Validación falló; Metiche reencola la misión para otro intento."
    if validation_plan == "failed":
        return flow, False, "Validación falló y la misión agotó sus reintentos."
    return flow, False, "Validación aprobada."


def evaluate_validation_plan(session: Session, task: Task) -> str:
    description = (task.description or "").lower()
    failed_rows = session.exec(select(Validation).where(Validation.task_id == task.id, Validation.status == "failed")).all()
    failed_count = len(failed_rows)
    if "[retry-once]" in description and failed_count == 0:
        return "retry"
    if "[always-fail]" in description:
        return "retry" if failed_count < MAX_VALIDATION_RETRIES - 1 else "failed"
    return "passed"

def build_validation_notes(task: Task, payload: TaskRunCreate, validation_status: str = "passed") -> str:
    if validation_status == "failed":
        return f"Validación local falló para {task.title} con modo {payload.execution_mode}."
    return f"Validación local completada para {task.title} con modo {payload.execution_mode}."

def build_chronicle(task: Task, decision: Decision, execution: Execution, validation: Validation) -> str:
    if validation.status == "failed":
        return f"Metiche intentó la misión {task.title} por la ruta {decision.chosen_path}, pero la validación cayó con estado failed. Jefe, esta vuelta quedó marcada para revisión."
    return f"Metiche recibió la misión {task.title} y la empujó por la ruta {decision.chosen_path}. La ejecución cerró con estado {execution.status} y la validación quedó en {validation.status}. Jefe, el laboratorio ya dejó memoria viva de este movimiento."


def get_engine_dispatch(session: Session, task_id: str) -> EngineDispatchRead | None:
    task = session.get(Task, task_id)
    route = session.exec(select(RouteResolution).where(RouteResolution.task_id == task_id).order_by(RouteResolution.created_at.desc())).first()
    if not task or not route:
        return None
    primary_engine, fallback_engine = determine_engine_plan(route.route_family)
    fallback_used = should_force_fallback(task, primary_engine) and fallback_engine is not None
    final_engine = fallback_engine if fallback_used and fallback_engine else primary_engine
    dispatch_status = "fallback_completed" if fallback_used else "completed"
    return EngineDispatchRead(
        id=f"dispatch-{task_id}",
        task_id=task_id,
        route_resolution_id=route.id,
        primary_engine=primary_engine,
        fallback_engine=fallback_engine,
        final_engine=final_engine,
        fallback_used=fallback_used,
        dispatch_status=dispatch_status,
        created_at=route.created_at,
    )


def determine_engine_plan(chosen_path: str) -> tuple[str, str | None]:
    if chosen_path == "reasoner_whatsapp":
        return "deepseek_reasoner", "metiche_chat"
    if chosen_path in {"metiche_planning", "metiche_direct"}:
        return "metiche_chat", "swarm_runtime"
    return "swarm_runtime", "metiche_chat"


def should_force_fallback(task: Task, primary_engine: str) -> bool:
    description = (task.description or "").lower()
    if "[force-fallback]" in description:
        return True
    if "[reasoner-fail]" in description and primary_engine == "deepseek_reasoner":
        return True
    if "[chat-fail]" in description and primary_engine == "metiche_chat":
        return True
    if "[swarm-fail]" in description and primary_engine == "swarm_runtime":
        return True
    return False


def get_task_escalation(session: Session, task_id: str) -> EscalationRead | None:
    task = session.get(Task, task_id)
    if not task:
        return None
    description = (task.description or "").lower()
    dispatch = get_engine_dispatch(session, task_id)
    if task.status == "failed":
        return EscalationRead(task_id=task_id, escalation_level="review", current_owner="human_review", next_owner=None, requires_review=True, reason="La misión agotó reintentos y pide revisión humana.")
    if dispatch and dispatch.fallback_used:
        return EscalationRead(task_id=task_id, escalation_level="fallback", current_owner=dispatch.final_engine, next_owner="human_review" if "[review-needed]" in description else None, requires_review="[review-needed]" in description, reason=f"El motor primario {dispatch.primary_engine} escaló a {dispatch.final_engine}.")
    if task.status == "retrying":
        return EscalationRead(task_id=task_id, escalation_level="retry", current_owner="worker", next_owner="metiche", requires_review=False, reason="La validación pidió un nuevo intento automático.")
    if task.task_type == "whatsapp":
        return EscalationRead(task_id=task_id, escalation_level="channel", current_owner="deepseek_reasoner", next_owner="metiche_chat", requires_review=False, reason="El canal WhatsApp mantiene ruta prioritaria con respaldo listo.")
    return EscalationRead(task_id=task_id, escalation_level="normal", current_owner=dispatch.final_engine if dispatch else "metiche", next_owner=None, requires_review=False, reason="La misión sigue su flujo normal sin escalamiento adicional.")


def build_operational_overview(session: Session) -> OperationalOverviewRead:
    tasks = session.exec(select(Task).order_by(Task.created_at.desc())).all()
    queue_entries = session.exec(select(QueueEntry)).all()
    routes = session.exec(select(RouteResolution)).all()
    status_counts: dict[str, int] = {}
    for task in tasks:
        status_counts[task.status] = status_counts.get(task.status, 0) + 1
    bucket_counts: dict[str, int] = {}
    for queue_entry in queue_entries:
        if queue_entry.status != "queued":
            continue
        bucket_counts[queue_entry.queue_bucket] = bucket_counts.get(queue_entry.queue_bucket, 0) + 1
    route_counts: dict[str, int] = {}
    for route in routes:
        route_counts[route.route_family] = route_counts.get(route.route_family, 0) + 1
    engine_counts: dict[str, int] = {}
    fallback_tasks = 0
    for task in tasks[:25]:
        dispatch = get_engine_dispatch(session, task.id)
        if not dispatch:
            continue
        engine_counts[dispatch.final_engine] = engine_counts.get(dispatch.final_engine, 0) + 1
        if dispatch.fallback_used:
            fallback_tasks += 1
    recent_tasks = [TaskRead.from_model(task) for task in tasks[:8]]
    return OperationalOverviewRead(generated_at=datetime.utcnow(), total_tasks=len(tasks), queue_depth=sum(1 for item in queue_entries if item.status == "queued"), retrying_tasks=status_counts.get("retrying", 0), failed_tasks=status_counts.get("failed", 0), fallback_tasks=fallback_tasks, status_counts=status_counts, bucket_counts=bucket_counts, engine_counts=engine_counts, route_counts=route_counts, recent_tasks=recent_tasks)
