-- Migration: add super_admin role support + login tracking for
-- account-sharing detection.
--
-- Usage:
--   psql "$DATABASE_URL" -f migrations/002_add_admin_and_login_tracking.sql

BEGIN;

-- 1. Enum type for role (mirrors app.models.models.UserRole)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole') THEN
        CREATE TYPE userrole AS ENUM ('owner', 'super_admin');
    END IF;
END$$;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS role userrole NOT NULL DEFAULT 'owner';

-- 2. Login event log  one row per successful login, used to flag an
--    account being used from an unusual number of distinct IPs/devices.
CREATE TABLE IF NOT EXISTS login_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    ip_address VARCHAR(64),
    user_agent VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_login_events_user_id ON login_events(user_id);
CREATE INDEX IF NOT EXISTS ix_login_events_created_at ON login_events(created_at);

COMMIT;

-- 3. Promote yourself to super_admin (run this manually  there's no
--    signup flow for admins on purpose, so no one can register their way
--    into platform access). Replace the email with your own account:
--
--   UPDATE users SET role = 'super_admin' WHERE email = 'you@example.com';
