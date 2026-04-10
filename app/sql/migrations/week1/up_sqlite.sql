-- Week 1 - Fase 2 (Enjambres y Canales)
-- Motor: SQLite
-- Objetivo: contratos de datos base para Semana 2.

PRAGMA foreign_keys = ON;
BEGIN TRANSACTION;

-- 1) Extensiones de task_events para trazabilidad de enjambres.
-- Nota: SQLite no soporta ADD COLUMN IF NOT EXISTS en versiones antiguas.
ALTER TABLE task_events ADD COLUMN swarm_id TEXT;
ALTER TABLE task_events ADD COLUMN cycle_id TEXT;
ALTER TABLE task_events ADD COLUMN correlation_id TEXT;
ALTER TABLE task_events ADD COLUMN client_key TEXT;
ALTER TABLE task_events ADD COLUMN severity TEXT;

-- 2) Extensiones de memory_entries (Opcion B).
ALTER TABLE memory_entries ADD COLUMN source TEXT NOT NULL DEFAULT 'system' CHECK (source IN ('system', 'channel', 'swarm'));
ALTER TABLE memory_entries ADD COLUMN related_channel TEXT;
ALTER TABLE memory_entries ADD COLUMN client_key TEXT;
ALTER TABLE memory_entries ADD COLUMN correlation_id TEXT;

-- 3) Tablas de enjambres.
CREATE TABLE IF NOT EXISTS swarms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(name) <= 255),
    goal TEXT NOT NULL,
    policy TEXT NOT NULL CHECK (policy IN ('majority', 'leader-follower', 'narrative-consensus')),
    status TEXT NOT NULL CHECK (status IN ('created', 'running', 'paused', 'completed', 'failed', 'cancelled')),
    parent_issue_id TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS swarm_agents (
    id TEXT PRIMARY KEY,
    swarm_id TEXT NOT NULL,
    agent_name TEXT NOT NULL CHECK (agent_name IN ('whatsapp', 'telegram', 'shopify', 'plane', 'dashboard', 'deepseek')),
    task_id TEXT,
    status TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'queued', 'running', 'done', 'failed', 'disabled')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (swarm_id, agent_name),
    FOREIGN KEY (swarm_id) REFERENCES swarms(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS swarm_cycles (
    id TEXT PRIMARY KEY,
    swarm_id TEXT NOT NULL,
    cycle_number INTEGER NOT NULL CHECK (cycle_number > 0),
    phase TEXT NOT NULL CHECK (phase IN ('plan', 'dispatch', 'validate', 'adjust', 'completed', 'failed')),
    outcome TEXT,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME,
    correlation_id TEXT,
    UNIQUE (swarm_id, cycle_number),
    FOREIGN KEY (swarm_id) REFERENCES swarms(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS swarm_votes (
    id TEXT PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    agent_name TEXT NOT NULL CHECK (agent_name IN ('whatsapp', 'telegram', 'shopify', 'plane', 'dashboard', 'deepseek')),
    vote TEXT NOT NULL CHECK (vote IN ('accept', 'reject', 'abstain')),
    argument TEXT CHECK (argument IS NULL OR length(argument) <= 2000),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (cycle_id, agent_name),
    FOREIGN KEY (cycle_id) REFERENCES swarm_cycles(id) ON DELETE CASCADE
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
