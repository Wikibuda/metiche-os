import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import Session, select

from app.domain.narrative.models import NarrativeEntryCreate
from app.domain.narrative.service import create_narrative_entry
from app.domain.swarm.models import (
    ALLOWED_AGENTS,
    ALLOWED_POLICIES,
    ALLOWED_SWARM_STATUS,
    Swarm,
    SwarmAgent,
    SwarmCreate,
    SwarmCycle,
    SwarmCycleRead,
    SwarmHistoryRead,
    SwarmRead,
    SwarmRunCreate,
    SwarmRunRead,
    SwarmSummaryRead,
    SwarmVote,
)
from app.services.dispatcher import DispatchResult, UnifiedTask, dispatch_unified_task


def create_swarm(session: Session, payload: SwarmCreate) -> SwarmRead:
    _validate_swarm_payload(payload)
    now = datetime.utcnow()
    swarm = Swarm(
        name=payload.name.strip(),
        goal=payload.goal.strip(),
        policy=payload.policy,
        status="created",
        parent_issue_id=payload.parent_issue_id,
        created_at=now,
        updated_at=now,
    )
    session.add(swarm)
    session.commit()
    session.refresh(swarm)

    agents: list[SwarmAgent] = []
    for agent_name in _dedupe_agents(payload.agents):
        row = SwarmAgent(
            swarm_id=swarm.id,
            agent_name=agent_name,
            status="idle",
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        agents.append(row)
    session.commit()
    for row in agents:
        session.refresh(row)
    return SwarmRead.from_model(swarm, agents)


def get_swarm(session: Session, swarm_id: str) -> SwarmRead | None:
    swarm = session.get(Swarm, swarm_id)
    if not swarm:
        return None
    agents = session.exec(select(SwarmAgent).where(SwarmAgent.swarm_id == swarm_id).order_by(SwarmAgent.agent_name)).all()
    return SwarmRead.from_model(swarm, agents)


def list_swarms(session: Session, limit: int = 20) -> list[SwarmSummaryRead]:
    rows = session.exec(select(Swarm).order_by(Swarm.updated_at.desc()).limit(limit)).all()
    output: list[SwarmSummaryRead] = []
    for swarm in rows:
        agents = session.exec(
            select(SwarmAgent).where(SwarmAgent.swarm_id == swarm.id).order_by(SwarmAgent.agent_name)
        ).all()
        output.append(SwarmSummaryRead.from_model(swarm, agents))
    return output


def run_swarm_cycle(session: Session, swarm_id: str, payload: SwarmRunCreate) -> SwarmRunRead | None:
    swarm = session.get(Swarm, swarm_id)
    if not swarm:
        return None

    agents = session.exec(select(SwarmAgent).where(SwarmAgent.swarm_id == swarm_id).order_by(SwarmAgent.agent_name)).all()
    if not agents:
        raise ValueError("swarm_without_agents")

    swarm.status = "running"
    swarm.updated_at = datetime.utcnow()
    session.add(swarm)
    session.commit()
    session.refresh(swarm)

    cycle_reads: list[SwarmCycleRead] = []
    stop_reason = "max_cycles_reached"
    decision = "reject"
    accepted_votes = 0
    rejected_votes = 0
    reject_streak = 0
    current_objective = payload.objective or swarm.goal

    for _ in range(payload.max_cycles):
        cycle, votes, decision, accepted_votes, rejected_votes, dispatch_results = _execute_single_cycle(
            session=session,
            swarm=swarm,
            agents=agents,
            objective=current_objective,
            payload=payload,
        )
        cycle_reads.append(SwarmCycleRead.from_model(cycle, votes))
        _emit_swarm_task_event(
            session=session,
            swarm=swarm,
            cycle=cycle,
            accepted_votes=accepted_votes,
            rejected_votes=rejected_votes,
            decision=decision,
            related_task_id=payload.related_task_id,
            client_key=payload.client_key,
            dispatch_results=dispatch_results,
        )
        _store_swarm_memory(
            session=session,
            swarm=swarm,
            cycle=cycle,
            decision=decision,
            accepted_votes=accepted_votes,
            rejected_votes=rejected_votes,
            client_key=payload.client_key,
            dispatch_results=dispatch_results,
        )
        _store_swarm_narrative(
            session=session,
            swarm=swarm,
            cycle=cycle,
            decision=decision,
            accepted_votes=accepted_votes,
            rejected_votes=rejected_votes,
            dispatch_results=dispatch_results,
        )
        if decision == "accept":
            stop_reason = "accepted_consensus"
            break
        reject_streak = reject_streak + 1 if decision == "reject" else 0
        if reject_streak >= 2:
            stop_reason = "reject_streak"
            break
        current_objective = f"Ajuste tras rechazo {reject_streak}: {payload.objective or swarm.goal}"

    final_status = "completed" if decision == "accept" else "failed"
    swarm.status = final_status
    swarm.updated_at = datetime.utcnow()
    for agent in agents:
        agent.status = "done" if decision == "accept" else "failed"
        agent.updated_at = datetime.utcnow()
        session.add(agent)
    session.add(swarm)
    session.commit()
    session.refresh(swarm)

    return SwarmRunRead(
        swarm=SwarmRead.from_model(swarm, agents),
        cycle=cycle_reads[-1],
        decision=decision,
        accepted_votes=accepted_votes,
        rejected_votes=rejected_votes,
        cycles_executed=len(cycle_reads),
        stop_reason=stop_reason,
        cycle_history=cycle_reads,
    )


def get_swarm_history(session: Session, swarm_id: str) -> SwarmHistoryRead | None:
    swarm = session.get(Swarm, swarm_id)
    if not swarm:
        return None
    agents = session.exec(select(SwarmAgent).where(SwarmAgent.swarm_id == swarm_id).order_by(SwarmAgent.agent_name)).all()
    cycles = session.exec(select(SwarmCycle).where(SwarmCycle.swarm_id == swarm_id).order_by(SwarmCycle.cycle_number)).all()
    cycle_reads: list[SwarmCycleRead] = []
    for cycle in cycles:
        votes = session.exec(select(SwarmVote).where(SwarmVote.cycle_id == cycle.id).order_by(SwarmVote.created_at)).all()
        cycle_reads.append(SwarmCycleRead.from_model(cycle, votes))
    return SwarmHistoryRead(
        swarm=SwarmRead.from_model(swarm, agents),
        total_cycles=len(cycle_reads),
        cycles=cycle_reads,
    )


def _dedupe_agents(agents: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in agents:
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _validate_swarm_payload(payload: SwarmCreate) -> None:
    if payload.policy not in ALLOWED_POLICIES:
        raise ValueError("invalid_policy")
    unique_agents = _dedupe_agents(payload.agents)
    if not unique_agents:
        raise ValueError("empty_agents")
    invalid_agents = [agent for agent in unique_agents if agent not in ALLOWED_AGENTS]
    if invalid_agents:
        raise ValueError(f"invalid_agents:{','.join(invalid_agents)}")


def _next_cycle_number(session: Session, swarm_id: str) -> int:
    rows = session.exec(select(SwarmCycle).where(SwarmCycle.swarm_id == swarm_id)).all()
    if not rows:
        return 1
    return max(item.cycle_number for item in rows) + 1


def _simulate_vote(agent_name: str, swarm: Swarm, payload: SwarmRunCreate) -> tuple[str, str]:
    context = f"{swarm.goal} {payload.objective or ''}".lower()
    if "riesgo" in context and agent_name in {"dashboard", "deepseek"}:
        return ("reject", "Se detecta riesgo alto y se sugiere ajuste antes de ejecutar.")
    if swarm.policy == "leader-follower" and agent_name != "deepseek":
        return ("abstain", "Modo leader-follower: agente en espera del lider.")
    return ("accept", "Alineado al objetivo del swarm para este ciclo.")


def _evaluate_decision(policy: str, accepted_votes: int, rejected_votes: int, total_votes: int) -> str:
    if total_votes <= 0:
        return "reject"
    if policy == "leader-follower":
        return "accept" if accepted_votes >= 1 else "reject"
    return "accept" if accepted_votes > rejected_votes else "reject"


def _execute_single_cycle(
    session: Session,
    swarm: Swarm,
    agents: list[SwarmAgent],
    objective: str,
    payload: SwarmRunCreate,
) -> tuple[SwarmCycle, list[SwarmVote], str, int, int, dict[str, DispatchResult]]:
    cycle_number = _next_cycle_number(session, swarm.id)
    cycle = SwarmCycle(
        swarm_id=swarm.id,
        cycle_number=cycle_number,
        phase="plan",
        outcome=f"Plan del ciclo {cycle_number}: {objective}",
        correlation_id=str(uuid4()),
    )
    session.add(cycle)
    session.commit()
    session.refresh(cycle)

    cycle.phase = "dispatch"
    now = datetime.utcnow()
    for agent in agents:
        agent.status = "running"
        agent.updated_at = now
        session.add(agent)
    session.add(cycle)
    session.commit()

    dispatch_results = _dispatch_cycle_actions(
        session=session,
        swarm=swarm,
        agents=agents,
        objective=objective,
        payload=payload,
        cycle=cycle,
    )

    votes: list[SwarmVote] = []
    vote_payload = payload.model_copy(update={"objective": objective})
    for agent in agents:
        dispatch_result = dispatch_results.get(agent.agent_name)
        if dispatch_result is not None:
            vote_value, reason = _vote_from_dispatch(agent.agent_name, dispatch_result)
        else:
            vote_value, reason = _simulate_vote(agent.agent_name, swarm, vote_payload)
        vote_row = SwarmVote(
            cycle_id=cycle.id,
            agent_name=agent.agent_name,
            vote=vote_value,
            argument=reason,
        )
        session.add(vote_row)
        votes.append(vote_row)
    cycle.phase = "validate"
    session.add(cycle)
    session.commit()
    for vote_row in votes:
        session.refresh(vote_row)

    accepted_votes = len([item for item in votes if item.vote == "accept"])
    rejected_votes = len([item for item in votes if item.vote == "reject"])
    decision = _evaluate_decision(swarm.policy, accepted_votes, rejected_votes, len(votes))

    cycle.phase = "adjust"
    cycle.outcome = (
        f"Decision del ciclo: {decision}. accept={accepted_votes}, reject={rejected_votes}. "
        f"dispatch={_dispatch_summary(dispatch_results)}"
    )
    session.add(cycle)
    session.commit()

    cycle.phase = "completed" if decision == "accept" else "failed"
    cycle.finished_at = datetime.utcnow()
    session.add(cycle)
    session.commit()
    session.refresh(cycle)
    return cycle, votes, decision, accepted_votes, rejected_votes, dispatch_results


def _dispatch_cycle_actions(
    session: Session,
    swarm: Swarm,
    agents: list[SwarmAgent],
    objective: str,
    payload: SwarmRunCreate,
    cycle: SwarmCycle,
) -> dict[str, DispatchResult]:
    results: dict[str, DispatchResult] = {}
    agent_names = {agent.agent_name for agent in agents}
    dispatchable_channels = {"whatsapp", "telegram"}
    channels_to_dispatch = sorted(dispatchable_channels.intersection(agent_names))
    if not channels_to_dispatch:
        return results
    client_key = (payload.client_key or "swarm-channel-demo").strip()
    for channel in channels_to_dispatch:
        task = UnifiedTask(
            task_type="send_message",
            channel=channel,
            client_key=client_key,
            message=objective,
            metadata={
                "swarm_id": swarm.id,
                "cycle_id": cycle.id,
                "cycle_number": cycle.cycle_number,
                "policy": swarm.policy,
            },
        )
        results[channel] = dispatch_unified_task(session, task)
    return results


def _vote_from_dispatch(agent_name: str, result: DispatchResult) -> tuple[str, str]:
    if result.success:
        return ("accept", f"{agent_name} envio mensaje correctamente y valida continuar el ciclo.")
    return ("reject", f"{agent_name} no pudo enviar mensaje ({result.error or 'error_desconocido'}).")


def _dispatch_summary(dispatch_results: dict[str, DispatchResult]) -> str:
    if not dispatch_results:
        return "none"
    chunks: list[str] = []
    for agent_name, result in dispatch_results.items():
        status = "ok" if result.success else "fail"
        retry_suffix = f"(r{result.retry_count})" if result.retry_count else ""
        chunks.append(f"{agent_name}:{status}{retry_suffix}")
    return ",".join(chunks)


def _emit_swarm_task_event(
    session: Session,
    swarm: Swarm,
    cycle: SwarmCycle,
    accepted_votes: int,
    rejected_votes: int,
    decision: str,
    related_task_id: str | None,
    client_key: str | None,
    dispatch_results: dict[str, DispatchResult],
) -> None:
    if not related_task_id:
        return
    payload = {
        "swarm_id": swarm.id,
        "cycle_id": cycle.id,
        "policy": swarm.policy,
        "accepted_votes": accepted_votes,
        "rejected_votes": rejected_votes,
        "decision": decision,
        "dispatch_results": {
            agent_name: {
                "success": result.success,
                "channel": result.channel,
                "task_type": result.task_type,
                "retry_count": result.retry_count,
                "final_status": result.final_status,
                "error": result.error,
                "details": result.details,
            }
            for agent_name, result in dispatch_results.items()
        },
    }
    importance = "high" if decision == "reject" else "low"
    severity = "warning" if decision == "reject" else "info"
    try:
        conn = session.connection()
        conn.execute(
            text(
                """
                INSERT INTO task_events (
                    id, task_id, execution_id, event_type, event_summary, importance_level,
                    wonder_level, payload_json, occurred_at, created_at,
                    swarm_id, cycle_id, correlation_id, client_key, severity
                ) VALUES (
                    :id, :task_id, NULL, :event_type, :event_summary, :importance_level,
                    :wonder_level, :payload_json, :occurred_at, :created_at,
                    :swarm_id, :cycle_id, :correlation_id, :client_key, :severity
                )
                """
            ),
            {
                "id": str(uuid4()),
                "task_id": related_task_id,
                "event_type": "swarm_cycle_result",
                "event_summary": f"Swarm {swarm.name} ciclo {cycle.cycle_number}: {decision}",
                "importance_level": importance,
                "wonder_level": 4 if decision == "accept" else 5,
                "payload_json": json.dumps(payload, ensure_ascii=False),
                "occurred_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
                "swarm_id": swarm.id,
                "cycle_id": cycle.id,
                "correlation_id": cycle.correlation_id,
                "client_key": client_key,
                "severity": severity,
            },
        )
        session.commit()
    except Exception:
        session.rollback()


def _store_swarm_memory(
    session: Session,
    swarm: Swarm,
    cycle: SwarmCycle,
    decision: str,
    accepted_votes: int,
    rejected_votes: int,
    client_key: str | None,
    dispatch_results: dict[str, DispatchResult],
) -> None:
    memory_text = (
        f"Swarm '{swarm.name}' cerró ciclo {cycle.cycle_number} con decision {decision}. "
        f"accept={accepted_votes}, reject={rejected_votes}, policy={swarm.policy}, "
        f"dispatch={_dispatch_summary(dispatch_results)}."
    )
    try:
        conn = session.connection()
        conn.execute(
            text(
                """
                INSERT INTO memory_entries (
                    id, task_id, task_event_id, source_narrative_entry_id, memory_kind, memory_text, salience_level,
                    created_at, source, related_channel, client_key, correlation_id
                ) VALUES (
                    :id, NULL, NULL, NULL, :memory_kind, :memory_text, :salience_level,
                    :created_at, :source, :related_channel, :client_key, :correlation_id
                )
                """
            ),
            {
                "id": str(uuid4()),
                "memory_kind": "episodic",
                "memory_text": memory_text,
                "salience_level": 5 if decision == "reject" else 4,
                "created_at": datetime.utcnow(),
                "source": "swarm",
                "related_channel": "swarm",
                "client_key": client_key,
                "correlation_id": cycle.correlation_id,
            },
        )
        session.commit()
    except Exception:
        session.rollback()
        # Fallback para esquemas donde Week 1 todavia no fue aplicada.
        try:
            conn = session.connection()
            conn.execute(
                text(
                    """
                    INSERT INTO memory_entries (
                        id, task_id, task_event_id, source_narrative_entry_id, memory_kind, memory_text, salience_level, created_at
                    ) VALUES (
                        :id, NULL, NULL, NULL, :memory_kind, :memory_text, :salience_level, :created_at
                    )
                    """
                ),
                {
                    "id": str(uuid4()),
                    "memory_kind": "episodic",
                    "memory_text": memory_text,
                    "salience_level": 5 if decision == "reject" else 4,
                    "created_at": datetime.utcnow(),
                },
            )
            session.commit()
        except Exception:
            session.rollback()


def _store_swarm_narrative(
    session: Session,
    swarm: Swarm,
    cycle: SwarmCycle,
    decision: str,
    accepted_votes: int,
    rejected_votes: int,
    dispatch_results: dict[str, DispatchResult],
) -> None:
    try:
        create_narrative_entry(
            session,
            NarrativeEntryCreate(
                title=f"Swarm {swarm.name} ciclo {cycle.cycle_number}: {decision}",
                body=(
                    f"El swarm '{swarm.name}' cerró ciclo {cycle.cycle_number} con decision {decision}. "
                    f"Votos accept={accepted_votes}, reject={rejected_votes}. "
                    f"Dispatch: {_dispatch_summary(dispatch_results)}."
                ),
                narrative_type="chronicle",
                wonder_level=4 if decision == "accept" else 5,
                narrator_code="metiche",
            ),
        )
    except Exception:
        session.rollback()


def validate_swarm_status(swarm: Swarm) -> None:
    if swarm.status not in ALLOWED_SWARM_STATUS:
        raise ValueError("invalid_swarm_status")
