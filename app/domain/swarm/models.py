from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


ALLOWED_POLICIES = {"majority", "leader-follower", "narrative-consensus"}
ALLOWED_AGENTS = {"whatsapp", "telegram", "shopify", "plane", "dashboard", "deepseek"}
ALLOWED_SWARM_STATUS = {"created", "running", "paused", "completed", "failed", "cancelled"}


class Swarm(SQLModel, table=True):
    __tablename__ = "swarms"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str
    goal: str
    policy: str = "narrative-consensus"
    status: str = "created"
    parent_issue_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SwarmAgent(SQLModel, table=True):
    __tablename__ = "swarm_agents"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    swarm_id: str = Field(foreign_key="swarms.id", index=True)
    agent_name: str
    task_id: str | None = None
    status: str = "idle"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SwarmCycle(SQLModel, table=True):
    __tablename__ = "swarm_cycles"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    swarm_id: str = Field(foreign_key="swarms.id", index=True)
    cycle_number: int
    phase: str = "plan"
    outcome: str | None = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    correlation_id: str | None = None


class SwarmVote(SQLModel, table=True):
    __tablename__ = "swarm_votes"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    cycle_id: str = Field(foreign_key="swarm_cycles.id", index=True)
    agent_name: str
    vote: str
    argument: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SwarmCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    goal: str = Field(min_length=10, max_length=2000)
    policy: str = "narrative-consensus"
    agents: list[str] = Field(min_length=1)
    parent_issue_id: str | None = None


class SwarmRunCreate(BaseModel):
    objective: str | None = None
    related_task_id: str | None = None
    client_key: str | None = None
    max_cycles: int = Field(default=1, ge=1, le=5)


class SwarmAgentRead(BaseModel):
    id: str
    swarm_id: str
    agent_name: str
    task_id: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, item: SwarmAgent) -> "SwarmAgentRead":
        return cls.model_validate(item, from_attributes=True)


class SwarmRead(BaseModel):
    id: str
    name: str
    goal: str
    policy: str
    status: str
    parent_issue_id: str | None = None
    created_at: datetime
    updated_at: datetime
    agents: list[SwarmAgentRead]

    @classmethod
    def from_model(cls, swarm: Swarm, agents: list[SwarmAgent]) -> "SwarmRead":
        return cls(
            id=swarm.id,
            name=swarm.name,
            goal=swarm.goal,
            policy=swarm.policy,
            status=swarm.status,
            parent_issue_id=swarm.parent_issue_id,
            created_at=swarm.created_at,
            updated_at=swarm.updated_at,
            agents=[SwarmAgentRead.from_model(item) for item in agents],
        )


class SwarmSummaryRead(BaseModel):
    id: str
    name: str
    goal: str
    policy: str
    status: str
    members: list[str]
    total_agents: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, swarm: Swarm, agents: list[SwarmAgent]) -> "SwarmSummaryRead":
        members = [agent.agent_name for agent in agents]
        return cls(
            id=swarm.id,
            name=swarm.name,
            goal=swarm.goal,
            policy=swarm.policy,
            status=swarm.status,
            members=members,
            total_agents=len(members),
            created_at=swarm.created_at,
            updated_at=swarm.updated_at,
        )


class SwarmVoteRead(BaseModel):
    id: str
    cycle_id: str
    agent_name: str
    vote: str
    argument: str | None = None
    created_at: datetime

    @classmethod
    def from_model(cls, item: SwarmVote) -> "SwarmVoteRead":
        return cls.model_validate(item, from_attributes=True)


class SwarmCycleRead(BaseModel):
    id: str
    swarm_id: str
    cycle_number: int
    phase: str
    outcome: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    correlation_id: str | None = None
    votes: list[SwarmVoteRead]

    @classmethod
    def from_model(cls, item: SwarmCycle, votes: list[SwarmVote]) -> "SwarmCycleRead":
        return cls(
            id=item.id,
            swarm_id=item.swarm_id,
            cycle_number=item.cycle_number,
            phase=item.phase,
            outcome=item.outcome,
            started_at=item.started_at,
            finished_at=item.finished_at,
            correlation_id=item.correlation_id,
            votes=[SwarmVoteRead.from_model(vote) for vote in votes],
        )


class SwarmRunRead(BaseModel):
    swarm: SwarmRead
    cycle: SwarmCycleRead
    decision: str
    accepted_votes: int
    rejected_votes: int
    cycles_executed: int
    stop_reason: str
    cycle_history: list[SwarmCycleRead]


class SwarmHistoryRead(BaseModel):
    swarm: SwarmRead
    total_cycles: int
    cycles: list[SwarmCycleRead]
