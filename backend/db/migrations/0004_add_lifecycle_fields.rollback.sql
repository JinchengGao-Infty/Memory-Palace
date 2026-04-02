-- Rollback for 0004_add_lifecycle_fields.sql
-- Requires SQLite >= 3.35.0 for DROP COLUMN support.

DROP INDEX IF EXISTS idx_memories_category;
DROP INDEX IF EXISTS idx_memories_layer_expires;
DROP INDEX IF EXISTS idx_memories_layer;

DROP TABLE IF EXISTS lifecycle_log;
DROP TABLE IF EXISTS memory_feedback;

ALTER TABLE memories DROP COLUMN expires_at;
ALTER TABLE memories DROP COLUMN confidence;
ALTER TABLE memories DROP COLUMN source;
ALTER TABLE memories DROP COLUMN category;
ALTER TABLE memories DROP COLUMN importance;
ALTER TABLE memories DROP COLUMN layer;
