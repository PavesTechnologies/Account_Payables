-- Manual migration: purchase_category.department_id (real FK ownership,
-- distinct from the pre-existing, currently-empty and unused
-- department_purchase_category many-to-many junction table, which this
-- migration does not touch).

ALTER TABLE ap.purchase_category
    ADD COLUMN IF NOT EXISTS department_id BIGINT;

-- Backfill existing categories by matching their code against the
-- department -> category-code assignment given for this migration.
-- Resolved via department.code lookups, never hardcoded department IDs.
-- A code with no existing row (e.g. IT_NETWORK, not yet created) is
-- simply a no-op here - this only assigns rows that already exist.
UPDATE ap.purchase_category pc
SET department_id = d.id
FROM ap.department d
WHERE d.code = 'IT'
  AND pc.code IN ('IT_HARDWARE', 'IT_SOFTWARE', 'IT_NETWORK', 'IT_SERVICES')
  AND pc.department_id IS NULL;

UPDATE ap.purchase_category pc
SET department_id = d.id
FROM ap.department d
WHERE d.code = 'HR'
  AND pc.code IN ('HR_RECRUITMENT', 'HR_BENEFITS', 'HR_TRAINING', 'HR_SERVICES')
  AND pc.department_id IS NULL;

UPDATE ap.purchase_category pc
SET department_id = d.id
FROM ap.department d
WHERE d.code = 'FIN'
  AND pc.code IN ('FIN_AUDIT', 'FIN_ACCOUNTING', 'FIN_TAX', 'FIN_CONSULTING')
  AND pc.department_id IS NULL;

UPDATE ap.purchase_category pc
SET department_id = d.id
FROM ap.department d
WHERE d.code = 'ADMIN'
  AND pc.code IN ('ADMIN_OFFICE', 'ADMIN_FACILITIES', 'ADMIN_TRAVEL', 'ADMIN_SECURITY')
  AND pc.department_id IS NULL;

-- Fail loudly rather than silently enforcing NOT NULL over unresolved rows.
DO $$
DECLARE
    unassigned_count INT;
BEGIN
    SELECT count(*) INTO unassigned_count FROM ap.purchase_category WHERE department_id IS NULL;
    IF unassigned_count > 0 THEN
        RAISE EXCEPTION
            'purchase_category has %% row(s) with no resolvable department_id - resolve them before this migration can proceed',
            unassigned_count;
    END IF;
END $$;

ALTER TABLE ap.purchase_category
    ALTER COLUMN department_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_purchase_category_department'
    ) THEN
        ALTER TABLE ap.purchase_category
            ADD CONSTRAINT fk_purchase_category_department
            FOREIGN KEY (department_id) REFERENCES ap.department(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_purchase_category_department ON ap.purchase_category (department_id);
