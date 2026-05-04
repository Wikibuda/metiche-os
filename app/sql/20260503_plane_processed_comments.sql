CREATE TABLE IF NOT EXISTS plane_processed_comments (
    comment_id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    author_email TEXT,
    command_text TEXT NOT NULL,
    action_name TEXT NOT NULL,
    params_json TEXT,
    status TEXT NOT NULL DEFAULT 'processing',
    result_json TEXT,
    error_text TEXT,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_plane_processed_comments_started_at
ON plane_processed_comments (started_at DESC);
