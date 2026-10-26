CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    identity TEXT NOT NULL,
    topics_json TEXT NOT NULL,
    keywords_json TEXT NOT NULL,
    timezone TEXT NOT NULL,
    push_time TEXT NOT NULL,
    push_enabled INTEGER NOT NULL CHECK (push_enabled IN (0, 1)),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('manual', 'scheduled')),
    local_date TEXT NOT NULL,
    content_md TEXT,
    trace_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    push_status TEXT NOT NULL CHECK (push_status IN ('pending', 'sent', 'failed', 'skipped')),
    error_message TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

INSERT OR IGNORE INTO settings (
    id, identity, topics_json, keywords_json, timezone,
    push_time, push_enabled, updated_at
) VALUES (
    1, 'AI 从业者', '["AI Agent"]', '[]', 'Asia/Shanghai',
    '09:00', 0, CURRENT_TIMESTAMP
);

