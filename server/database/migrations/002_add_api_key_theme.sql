-- Web Chat / Bubble theme per widget API key.
-- Applied automatically and idempotently by app.db_config.init_database() on
-- backend start; this file documents the change and can be run by hand:
--   psql "$DATABASE_URL" -f server/database/migrations/002_add_api_key_theme.sql
-- Rollback: ALTER TABLE api_keys DROP COLUMN IF EXISTS theme;
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS theme JSON;
