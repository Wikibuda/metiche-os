-- Week 1 rollback - Fase 2 (Enjambres y Canales)
-- Motor: PostgreSQL

BEGIN;

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

-- 3) Revertir extensiones en memory_entries.
ALTER TABLE memory_entries
    DROP CONSTRAINT IF EXISTS ck_memory_entries_source;

ALTER TABLE memory_entries
    DROP COLUMN IF EXISTS correlation_id,
    DROP COLUMN IF EXISTS client_key,
    DROP COLUMN IF EXISTS related_channel,
    DROP COLUMN IF EXISTS source;

-- 4) Revertir extensiones en task_events.
ALTER TABLE task_events
    DROP COLUMN IF EXISTS severity,
    DROP COLUMN IF EXISTS client_key,
    DROP COLUMN IF EXISTS correlation_id,
    DROP COLUMN IF EXISTS cycle_id,
    DROP COLUMN IF EXISTS swarm_id;

COMMIT;
