-- Manual migration for Phase 1 IN-APP notifications (ap.notification).
--
-- This codebase has no migration tool: Base.metadata.create_all() (main.py)
-- creates ap.notification automatically on app startup because the model is
-- registered in Data_Access_Layer/models/__init__.py. This file creates the
-- exact same table/indexes by hand for environments where it should be
-- applied explicitly (or before the app starts). Every statement is guarded,
-- so it is safe to re-run and safe to run after create_all() already ran.
--
-- No existing AP table is altered.

CREATE TABLE IF NOT EXISTS ap.notification (
    id                  BIGSERIAL    NOT NULL,
    recipient_user_uuid UUID         NOT NULL,
    notification_type   VARCHAR(60)  NOT NULL,
    title               VARCHAR(255) NOT NULL,
    message             TEXT         NOT NULL,
    priority            VARCHAR(10)  NOT NULL DEFAULT 'MEDIUM',
    entity_type         VARCHAR(50)  NOT NULL,
    entity_id           VARCHAR(64)  NOT NULL,
    is_read             BOOLEAN      NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    dedupe_key          VARCHAR(512) NOT NULL,
    read_at             TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,
    triggered_by        VARCHAR(100),
    payload             JSONB,
    CONSTRAINT notification_pkey PRIMARY KEY (id)
);

-- Postgres has no "ADD CONSTRAINT IF NOT EXISTS" - wrapped to stay re-runnable.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'notification_dedupe_key_key') THEN
        ALTER TABLE ap.notification
            ADD CONSTRAINT notification_dedupe_key_key UNIQUE (dedupe_key);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_notification_priority') THEN
        ALTER TABLE ap.notification
            ADD CONSTRAINT chk_notification_priority
            CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_notification_recipient        ON ap.notification (recipient_user_uuid);
CREATE INDEX IF NOT EXISTS idx_notification_recipient_unread ON ap.notification (recipient_user_uuid, is_read);
CREATE INDEX IF NOT EXISTS idx_notification_created_at       ON ap.notification (created_at);
CREATE INDEX IF NOT EXISTS idx_notification_entity           ON ap.notification (entity_type, entity_id);
