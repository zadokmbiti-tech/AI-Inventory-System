-- Migration: add Kenyan VAT/tax fields to products, sales, sale_items
-- Run this once against your existing database (the app's Base.metadata.create_all()
-- only creates NEW tables on startup — it will NOT add these columns to tables
-- that already exist, so this migration is required).
--
-- Usage:
--   psql "$DATABASE_URL" -f migrations/001_add_vat_tax_fields.sql

BEGIN;

-- 1. Enum type for tax category (mirrors app.models.models.TaxCategory)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taxcategory') THEN
        CREATE TYPE taxcategory AS ENUM ('STANDARD', 'REDUCED', 'ZERO_RATED', 'EXEMPT');
    END IF;
END$$;

-- 2. Products: tax category + rate (default = current 16% Kenya standard VAT rate)
ALTER TABLE products
    ADD COLUMN IF NOT EXISTS tax_category taxcategory NOT NULL DEFAULT 'STANDARD',
    ADD COLUMN IF NOT EXISTS tax_rate DOUBLE PRECISION NOT NULL DEFAULT 16.0;

-- 3. Sales: split total_amount into subtotal (net) + tax_amount (VAT collected)
ALTER TABLE sales
    ADD COLUMN IF NOT EXISTS subtotal_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tax_amount DOUBLE PRECISION NOT NULL DEFAULT 0;

-- Backfill existing sales: treat historical total_amount as net (no VAT was tracked before)
UPDATE sales SET subtotal_amount = total_amount WHERE subtotal_amount = 0;

-- 4. Sale items: freeze the tax category/rate/amount applied at time of sale
ALTER TABLE sale_items
    ADD COLUMN IF NOT EXISTS tax_category taxcategory NOT NULL DEFAULT 'STANDARD',
    ADD COLUMN IF NOT EXISTS tax_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tax_amount DOUBLE PRECISION NOT NULL DEFAULT 0;

COMMIT;

-- Note: existing historical sale_items are backfilled with tax_rate=0 / tax_amount=0
-- because we don't know what, if any, VAT was actually charged on those past sales.
-- Only sales recorded AFTER this migration will carry accurate VAT figures.

-- 5. Licenses table (new table — created automatically by the app's
--    Base.metadata.create_all() on startup, but included here for completeness
--    if you'd rather apply it explicitly / ahead of time).
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'licensestatus') THEN
        CREATE TYPE licensestatus AS ENUM ('ACTIVE', 'EXPIRED', 'REVOKED');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS licenses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    license_key VARCHAR(40) NOT NULL UNIQUE,
    status licensestatus NOT NULL DEFAULT 'ACTIVE',
    plan VARCHAR(50) DEFAULT 'monthly',
    amount_paid DOUBLE PRECISION,
    mpesa_receipt VARCHAR(100),
    issued_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_licenses_user_id ON licenses(user_id);
CREATE INDEX IF NOT EXISTS ix_licenses_license_key ON licenses(license_key);

COMMIT;

-- 6. Give existing users (registered before licensing existed) a 30-day
--    grace license so they aren't locked out immediately after this deploy.
--    Skip this if you'd rather they renew manually right away.
INSERT INTO licenses (user_id, license_key, status, plan, issued_at, expires_at)
SELECT
    u.id,
    'SSA-' || upper(substr(md5(random()::text || u.id::text), 1, 4)) || '-' ||
              upper(substr(md5(random()::text || u.id::text || '2'), 1, 4)) || '-' ||
              upper(substr(md5(random()::text || u.id::text || '3'), 1, 4)),
    'ACTIVE',
    'grandfathered',
    now(),
    now() + interval '30 days'
FROM users u
WHERE NOT EXISTS (SELECT 1 FROM licenses l WHERE l.user_id = u.id);

-- 7. Widen document_records.file_path — Vercel Blob URLs are longer than
--    the local disk paths this column originally stored.
ALTER TABLE document_records
    ALTER COLUMN file_path TYPE VARCHAR(1000);



