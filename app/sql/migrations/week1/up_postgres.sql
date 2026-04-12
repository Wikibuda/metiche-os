-- Week 1 - Fase 2 (Enjambres y Canales)
-- Motor: PostgreSQL
-- Objetivo: contratos de datos base para Semana 2.

BEGIN;

-- 1) Extensiones de task_events para trazabilidad de enjambres.
ALTER TABLE task_events
    ADD COLUMN IF NOT EXISTS swarm_id TEXT,
    ADD COLUMN IF NOT EXISTS cycle_id TEXT,
    ADD COLUMN IF NOT EXISTS correlation_id TEXT,
    ADD COLUMN IF NOT EXISTS client_key TEXT,
    ADD COLUMN IF NOT EXISTS severity TEXT;

-- 2) Extensiones de memory_entries (Opcion B).
ALTER TABLE memory_entries
    ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'system',
    ADD COLUMN IF NOT EXISTS related_channel TEXT,
    ADD COLUMN IF NOT EXISTS client_key TEXT,
    ADD COLUMN IF NOT EXISTS correlation_id TEXT;

UPDATE memory_entries
SET source = 'system'
WHERE source IS NULL;

ALTER TABLE memory_entries
    ALTER COLUMN source SET NOT NULL;

ALTER TABLE memory_entries
    DROP CONSTRAINT IF EXISTS ck_memory_entries_source;

ALTER TABLE memory_entries
    ADD CONSTRAINT ck_memory_entries_source
    CHECK (source IN ('system', 'channel', 'swarm'));

-- 3) Tablas de enjambres.
CREATE TABLE IF NOT EXISTS swarms (
    id TEXT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    goal TEXT NOT NULL,
    policy VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    parent_issue_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (policy IN ('majority', 'leader-follower', 'narrative-consensus')),
    CHECK (status IN ('created', 'running', 'paused', 'completed', 'failed', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS swarm_agents (
    id TEXT PRIMARY KEY,
    swarm_id TEXT NOT NULL REFERENCES swarms(id) ON DELETE CASCADE,
    agent_name VARCHAR(50) NOT NULL,
    task_id TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'idle',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (agent_name IN ('whatsapp', 'telegram', 'shopify', 'plane', 'dashboard', 'deepseek')),
    CHECK (status IN ('idle', 'queued', 'running', 'done', 'failed', 'disabled')),
    UNIQUE (swarm_id, agent_name)
);

CREATE TABLE IF NOT EXISTS swarm_cycles (
    id TEXT PRIMARY KEY,
    swarm_id TEXT NOT NULL REFERENCES swarms(id) ON DELETE CASCADE,
    cycle_number INTEGER NOT NULL,
    phase VARCHAR(50) NOT NULL,
    outcome TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    correlation_id TEXT,
    CHECK (cycle_number > 0),
    CHECK (phase IN ('plan', 'dispatch', 'validate', 'adjust', 'completed', 'failed')),
    UNIQUE (swarm_id, cycle_number)
);

CREATE TABLE IF NOT EXISTS swarm_votes (
    id TEXT PRIMARY KEY,
    cycle_id TEXT NOT NULL REFERENCES swarm_cycles(id) ON DELETE CASCADE,
    agent_name VARCHAR(50) NOT NULL,
    vote VARCHAR(20) NOT NULL,
    argument VARCHAR(2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (agent_name IN ('whatsapp', 'telegram', 'shopify', 'plane', 'dashboard', 'deepseek')),
    CHECK (vote IN ('accept', 'reject', 'abstain')),
    CHECK (argument IS NULL OR LENGTH(argument) <= 2000),
    UNIQUE (cycle_id, agent_name)
);

-- 4) Indices solicitados.
CREATE INDEX IF NOT EXISTS idx_memory_client
    ON memory_entries (client_key);

CREATE INDEX IF NOT EXISTS idx_memory_correlation
    ON memory_entries (correlation_id);

CREATE INDEX IF NOT EXISTS idx_memory_multicanal
    ON memory_entries (source, related_channel, client_key);

CREATE INDEX IF NOT EXISTS idx_task_events_swarm
    ON task_events (swarm_id, cycle_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_swarms_status
    ON swarms (status);

CREATE INDEX IF NOT EXISTS idx_swarm_agents_swarm
    ON swarm_agents (swarm_id, status);

CREATE INDEX IF NOT EXISTS idx_swarm_cycles_swarm
    ON swarm_cycles (swarm_id, cycle_number);

CREATE INDEX IF NOT EXISTS idx_swarm_votes_cycle
    ON swarm_votes (cycle_id);

COMMIT;
