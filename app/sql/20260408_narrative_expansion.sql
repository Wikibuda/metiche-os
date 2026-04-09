-- metiche-os additive DDL for narrative/memory layer expansion.
-- This script only creates new tables; it does not alter existing ones.
-- SQLite-compatible DDL.

PRAGMA foreign_keys = ON;

-- task_events:
-- Timeline of operational events emitted from task/execution activity.
-- Used as source stream for memory extraction and candidate narration.
CREATE TABLE IF NOT EXISTS task_events (
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

CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id);
CREATE INDEX IF NOT EXISTS idx_task_events_occurred_at ON task_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_events_importance ON task_events(importance_level, wonder_level);

-- memory_entries:
-- Durable memory atoms built from events and/or narrative entries.
-- These records are intended for later retrieval and composition.
CREATE TABLE IF NOT EXISTS memory_entries (
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

CREATE INDEX IF NOT EXISTS idx_memory_entries_task_id ON memory_entries(task_id);
CREATE INDEX IF NOT EXISTS idx_memory_entries_salience ON memory_entries(salience_level DESC);

-- narrative_candidates:
-- Candidate chronicles proposed by selector rules before publication.
-- Created from high-signal events and optionally linked memory entries.
CREATE TABLE IF NOT EXISTS narrative_candidates (
    id TEXT PRIMARY KEY,
    task_event_id TEXT NOT NULL,
    source_memory_entry_id TEXT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    narrative_type TEXT NOT NULL DEFAULT 'chronicle',
    wonder_level INTEGER NOT NULL DEFAULT 3,
    selector_reason TEXT NOT NULL,
    selector_version TEXT NOT NULL DEFAULT 'v0',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    selected_at DATETIME,
    FOREIGN KEY (task_event_id) REFERENCES task_events(id),
    FOREIGN KEY (source_memory_entry_id) REFERENCES memory_entries(id)
);

CREATE INDEX IF NOT EXISTS idx_narrative_candidates_status ON narrative_candidates(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_narrative_candidates_event ON narrative_candidates(task_event_id);

-- narrative_collections:
-- Curated groups of candidates and/or published narrative entries.
-- Intended for daily summaries, thematic compilations, or release batches.
CREATE TABLE IF NOT EXISTS narrative_collections (
    id TEXT PRIMARY KEY,
    collection_key TEXT NOT NULL UNIQUE,
    collection_type TEXT NOT NULL DEFAULT 'daily',
    title TEXT NOT NULL,
    description TEXT,
    curator_code TEXT NOT NULL DEFAULT 'metiche',
    status TEXT NOT NULL DEFAULT 'open',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_narrative_collections_type ON narrative_collections(collection_type, created_at DESC);

-- narrative_collection_items:
-- Ordered members of a collection, linked to either candidate or final narrative entry.
-- Exactly one of candidate_id / narrative_entry_id should be present at insertion time.
CREATE TABLE IF NOT EXISTS narrative_collection_items (
    id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL,
    candidate_id TEXT,
    narrative_entry_id TEXT,
    item_order INTEGER NOT NULL DEFAULT 1,
    include_reason TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (collection_id) REFERENCES narrative_collections(id),
    FOREIGN KEY (candidate_id) REFERENCES narrative_candidates(id),
    FOREIGN KEY (narrative_entry_id) REFERENCES narrativeentry(id),
    UNIQUE (collection_id, item_order)
);

CREATE INDEX IF NOT EXISTS idx_collection_items_collection ON narrative_collection_items(collection_id, item_order);

-- narrative_projections:
-- Persisted outputs generated from collections (markdown, terminal snapshot, etc.).
-- Supports traceability from source collection to rendered artifact.
CREATE TABLE IF NOT EXISTS narrative_projections (
    id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL,
    projection_type TEXT NOT NULL DEFAULT 'bitacora_markdown',
    output_path TEXT,
    content_snapshot TEXT,
    projector_code TEXT NOT NULL DEFAULT 'metiche',
    projected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (collection_id) REFERENCES narrative_collections(id)
);

CREATE INDEX IF NOT EXISTS idx_narrative_projections_collection ON narrative_projections(collection_id, projected_at DESC);
