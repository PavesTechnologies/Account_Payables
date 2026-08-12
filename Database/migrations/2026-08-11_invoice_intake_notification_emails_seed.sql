-- Migration: Seed the INVOICE_INTAKE_NOTIFICATION_EMAILS system_configuration
-- key used by the invoice vendor-not-found / vendor-auto-onboarding
-- notification flow (Backend.Business_Layer.utils.notifications
-- .resolve_invoice_intake_recipients).
--
-- Context: this project has no migration tool (no Alembic) — schema is
-- hand-maintained in Database/ap_schema.sql and applied via
-- Base.metadata.create_all() at app startup, which only creates missing
-- tables and never seeds/alters existing ones. ap_schema.sql has been
-- updated with this same row for any future fresh deployment; this file
-- seeds it into an already-deployed database.
--
-- Value is comma-separated so additional recipients can be appended later
-- with a plain UPDATE, without another migration.

BEGIN;

INSERT INTO ap.system_configuration (config_key, config_value, data_type, description)
VALUES (
    'INVOICE_INTAKE_NOTIFICATION_EMAILS',
    'Jagadish.Pannala@pavestechnologies.com',
    'STRING',
    'Email recipients for invoice vendor-not-found and vendor-auto-onboarding notifications'
)
ON CONFLICT (config_key) DO NOTHING;

COMMIT;
