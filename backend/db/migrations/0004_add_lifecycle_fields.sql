-- Cortex lifecycle fields for memories, feedback tracking, and lifecycle logging.;

ALTER TABLE memories ADD COLUMN layer TEXT NOT NULL DEFAULT 'core';
ALTER TABLE memories ADD COLUMN importance REAL NOT NULL DEFAULT 0.5;
ALTER TABLE memories ADD COLUMN category TEXT;
ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE memories ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0;
ALTER TABLE memories ADD COLUMN expires_at DATETIME;

CREATE INDEX IF NOT EXISTS idx_memories_layer
    ON memories(layer);

CREATE INDEX IF NOT EXISTS idx_memories_layer_expires
    ON memories(layer, expires_at);

CREATE INDEX IF NOT EXISTS idx_memories_category
    ON memories(category);

CREATE TABLE IF NOT EXISTS memory_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    signal TEXT NOT NULL CHECK(signal IN ('helpful', 'outdated', 'wrong')),
    reason TEXT,
    created_at DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS lifecycle_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase TEXT NOT NULL,
    details TEXT,
    created_at DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
