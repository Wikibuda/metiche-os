from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel
from sqlmodel import Field, SQLModel

from app.domain.narrative.models import NarrativeEntryRead


class Task(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str
    description: Optional[str] = None
    execution_mode: str = Field(default="queued")
    task_type: str = Field(default="planning")
    status: str = Field(default="new")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    execution_mode: str = "queued"
    task_type: str = "planning"


class TaskRead(BaseModel):
    id: str
    title: str
    description: str | None = None
    execution_mode: str
    task_type: str
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, task: Task) -> "TaskRead":
        return cls.model_validate(task, from_attributes=True)



class Decision(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    decision_type: str = Field(default="routing")
    chosen_path: str
    rationale: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Execution(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    decision_id: str = Field(foreign_key="decision.id", index=True)
    actor_code: str = Field(default="metiche")
    status: str = Field(default="running")
    summary: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class Validation(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    execution_id: str = Field(foreign_key="execution.id", index=True)
    validator_code: str = Field(default="metiche")
    status: str = Field(default="pending")
    notes: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaskRunCreate(BaseModel):
    title: str
    description: str | None = None
    execution_mode: str = "queued"
    task_type: str = "operational"
    requested_by: str = "gus"


class DecisionRead(BaseModel):
    id: str
    task_id: str
    decision_type: str
    chosen_path: str
    rationale: str
    created_at: datetime

    @classmethod
    def from_model(cls, decision: Decision) -> "DecisionRead":
        return cls.model_validate(decision, from_attributes=True)


class ExecutionRead(BaseModel):
    id: str
    task_id: str
    decision_id: str
    actor_code: str
    status: str
    summary: str
    started_at: datetime
    completed_at: datetime | None = None

    @classmethod
    def from_model(cls, execution: Execution) -> "ExecutionRead":
        return cls.model_validate(execution, from_attributes=True)


class ValidationRead(BaseModel):
    id: str
    task_id: str
    execution_id: str
    validator_code: str
    status: str
    notes: str
    created_at: datetime

    @classmethod
    def from_model(cls, validation: Validation) -> "ValidationRead":
        return cls.model_validate(validation, from_attributes=True)


class TaskFlowRead(BaseModel):
    task: TaskRead
    decision: DecisionRead
    execution: ExecutionRead
    validation: ValidationRead
    narrative: NarrativeEntryRead | None = None


class QueueEntry(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    priority: str = Field(default="medium")
    queue_bucket: str = Field(default="medium")
    status: str = Field(default="queued")
    enqueued_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TaskEnqueueCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str = "medium"
    task_type: str = "operational"


class QueueEntryRead(BaseModel):
    id: str
    task_id: str
    priority: str
    queue_bucket: str
    status: str
    enqueued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_model(cls, queue_entry: QueueEntry) -> "QueueEntryRead":
        return cls.model_validate(queue_entry, from_attributes=True)


class TaskQueueProcessRead(BaseModel):
    queue_entry: QueueEntryRead
    flow: TaskFlowRead


class RouteResolution(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    channel: str = Field(default="internal")
    route_family: str
    target_engine: str
    target_actor: str = Field(default="metiche")
    matched_rule_code: str
    rationale: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RouteResolutionRead(BaseModel):
    id: str
    task_id: str
    channel: str
    route_family: str
    target_engine: str
    target_actor: str
    matched_rule_code: str
    rationale: str
    created_at: datetime

    @classmethod
    def from_model(cls, item: RouteResolution) -> "RouteResolutionRead":
        return cls.model_validate(item, from_attributes=True)


class TaskQueueProcessRead(BaseModel):
    queue_entry: QueueEntryRead
    flow: TaskFlowRead
    retry_scheduled: bool = False
    message: str | None = None


class EngineDispatch(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    route_resolution_id: str = Field(foreign_key="routeresolution.id", index=True)
    primary_engine: str
    fallback_engine: str | None = None
    final_engine: str
    fallback_used: bool = Field(default=False)
    dispatch_status: str = Field(default="completed")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EngineDispatchRead(BaseModel):
    id: str
    task_id: str
    route_resolution_id: str
    primary_engine: str
    fallback_engine: str | None = None
    final_engine: str
    fallback_used: bool
    dispatch_status: str
    created_at: datetime

    @classmethod
    def from_model(cls, item: EngineDispatch) -> "EngineDispatchRead":
        return cls.model_validate(item, from_attributes=True)



class EscalationRead(BaseModel):
    task_id: str
    escalation_level: str
    current_owner: str
    next_owner: str | None = None
    requires_review: bool = False
    reason: str


class OperationalOverviewRead(BaseModel):
    generated_at: datetime
    total_tasks: int
    queue_depth: int
    retrying_tasks: int
    failed_tasks: int
    fallback_tasks: int
    status_counts: dict[str, int]
    bucket_counts: dict[str, int]
    engine_counts: dict[str, int]
    route_counts: dict[str, int]
    recent_tasks: list[TaskRead]
