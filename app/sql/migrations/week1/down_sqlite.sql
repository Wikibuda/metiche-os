-- Week 1 rollback - Fase 2 (Enjambres y Canales)
-- Motor: SQLite
-- Estrategia: reconstruccion de tablas para remover columnas agregadas.

PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

-- 1) Indices.
DROP INDEX IF EXISTS idx_swarm_votes_cycle;
DROP INDEX IF EXISTS idx_swarm_cycles_swarm;
DROP INDEX IF EXISTS idx_swarm_agents_swarm;
DROP INDEX IF EXISTS idx_swarms_status;
DROP INDEX IF EXISTS idx_task_events_swarm;
DROP INDEX IF EXISTS idx_memory_multicanal;
DROP INDEX IF EXISTS idx_memory_correlation;
DROP INDEX IF EXISTS idx_memory_client;

-- 2) Tablas de enjambres.
DROP TABLE IF EXISTS swarm_votes;
DROP TABLE IF EXISTS swarm_cycles;
DROP TABLE IF EXISTS swarm_agents;
DROP TABLE IF EXISTS swarms;

-- 3) Revertir task_events a estructura base (sin columnas swarm/correlacion extra).
CREATE TABLE task_events__rollback (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    execution_id TEXT,
    event_type TEXT NOT NULL,
    event_summary TEXT NOT NULL,
    importance_level TEXT NOT NULL DEFAULT 'medium',
    wonder_level INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT,
    occurred_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES task(id),
    FOREIGN KEY (execution_id) REFERENCES execution(id)
);

INSERT INTO task_events__rollback (
    id, task_id, execution_id, event_type, event_summary, importance_level,
    wonder_level, payload_json, occurred_at, created_at
)
SELECT
    id, task_id, execution_id, event_type, event_summary, importance_level,
    wonder_level, payload_json, occurred_at, created_at
FROM task_events;

DROP TABLE task_events;
ALTER TABLE task_events__rollback RENAME TO task_events;

-- Reaplicar indices base de task_events definidos en la migracion narrativa original.
CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id);
CREATE INDEX IF NOT EXISTS idx_task_events_occurred_at ON task_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_events_importance ON task_events(importance_level, wonder_level);

-- 4) Revertir memory_entries a estructura base (sin columnas opcion B).
CREATE TABLE memory_entries__rollback (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    task_event_id TEXT,
    source_narrative_entry_id TEXT,
    memory_kind TEXT NOT NULL DEFAULT 'episodic',
    memory_text TEXT NOT NULL,
    salience_level INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES task(id),
    FOREIGN KEY (task_event_id) REFERENCES task_events(id),
    FOREIGN KEY (source_narrative_entry_id) REFERENCES narrativeentry(id)
);

INSERT INTO memory_entries__rollback (
    id, task_id, task_event_id, source_narrative_entry_id,
    memory_kind, memory_text, salience_level, created_at
)
SELECT
    id, task_id, task_event_id, source_narrative_entry_id,
    memory_kind, memory_text, salience_level, created_at
FROM memory_entries;

DROP TABLE memory_entries;
ALTER TABLE memory_entries__rollback RENAME TO memory_entries;

-- Reaplicar indices base de memory_entries definidos en la migracion narrativa original.
CREATE INDEX IF NOT EXISTS idx_memory_entries_task_id ON memory_entries(task_id);
CREATE INDEX IF NOT EXISTS idx_memory_entries_salience ON memory_entries(salience_level DESC);

COMMIT;
PRAGMA foreign_keys = ON;
