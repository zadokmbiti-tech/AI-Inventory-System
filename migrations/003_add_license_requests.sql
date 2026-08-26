-- Migration: license requests (approval-gated activation).
--
-- Registration no longer auto-grants a trial license, and there's no
-- self-service instant renewal  a business must ask, and only a
-- super_admin activating them from the Admin panel actually grants access.
--
-- Usage:
--   psql "$DATABASE_URL" -f migrations/003_add_license_requests.sql

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'licenserequeststatus') THEN
        CREATE TYPE licenserequeststatus AS ENUM ('PENDING', 'FULFILLED', 'DISMISSED');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS license_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    plan VARCHAR(50) DEFAULT 'monthly',
    message TEXT,
    status licenserequeststatus NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_license_requests_user_id ON license_requests(user_id);

COMMIT;
