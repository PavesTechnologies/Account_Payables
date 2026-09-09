-- Manual migration for the UOM master + PR-line custom UOM support.
-- This codebase has no migration tool (Base.metadata.create_all only creates
-- missing tables and never alters existing ones), so:
--   * ap.unit_of_measure is a new table -> created automatically by
--     create_all() the next time the app starts (model registered via
--     Data_Access_Layer/models/__init__.py -> models/master.py).
--   * The ALTER TABLE below and the seed INSERTs are applied manually, the
--     same way status_master rows and prior schema changes already are
--     (see migration_rfq_workflow.sql / migration_purchase_category_department.sql).

ALTER TABLE ap.purchase_requisition_line
    ADD COLUMN IF NOT EXISTS is_custom_uom BOOLEAN NOT NULL DEFAULT false;

-- Standard UOM seed data. Idempotent - safe to re-run.
INSERT INTO ap.unit_of_measure (code, name, category, allows_decimal, is_active) VALUES
    ('EA',   'Each',           'COUNT',     false, true),
    ('PCS',  'Piece',          'COUNT',     false, true),
    ('UNIT', 'Unit',           'COUNT',     false, true),
    ('SET',  'Set',            'COUNT',     false, true),
    ('BOX',  'Box',            'PACKAGING', false, true),
    ('PACK', 'Pack',           'PACKAGING', false, true),
    ('CTN',  'Carton',         'PACKAGING', false, true),
    ('ROLL', 'Roll',           'PACKAGING', false, true),
    ('KG',   'Kilogram',       'WEIGHT',    true,  true),
    ('G',    'Gram',           'WEIGHT',    true,  true),
    ('M',    'Meter',          'LENGTH',    true,  true),
    ('CM',   'Centimeter',     'LENGTH',    true,  true),
    ('L',    'Liter',          'VOLUME',    true,  true),
    ('ML',   'Milliliter',     'VOLUME',    true,  true),
    ('SQM',  'Square Meter',   'AREA',      true,  true),
    ('SQFT', 'Square Foot',    'AREA',      true,  true),
    ('HR',   'Hour',           'TIME',      true,  true),
    ('DAY',  'Day',            'TIME',      true,  true),
    ('MON',  'Month',          'TIME',      true,  true),
    ('YR',   'Year',           'TIME',      true,  true)
ON CONFLICT (code) DO NOTHING;

-- Timeline queries filter ap.audit_log by (table_name, record_id) - already
-- covered by idx_audit_table_record - and order by changed_at; this index
-- covers that ordering/range side.
CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at ON ap.audit_log (changed_at);
