-- Adds invoice_line.po_line_id (nullable FK to purchase_order_line.po_line_id)
-- to support line-level 2-way/3-way PO/GRN/Invoice matching, mirroring the
-- existing goods_receipt_line.po_line_id pattern. Additive and idempotent:
-- safe to run against a database that already has it.
--
-- Approved change — see backend/database audit (2026-08-13). Does not
-- touch any existing column, does not drop/alter/delete data.

ALTER TABLE ap.invoice_line
    ADD COLUMN IF NOT EXISTS po_line_id INTEGER NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_schema = 'ap'
          AND table_name = 'invoice_line'
          AND constraint_name = 'invoice_line_po_line_id_fkey'
    ) THEN
        ALTER TABLE ap.invoice_line
            ADD CONSTRAINT invoice_line_po_line_id_fkey
            FOREIGN KEY (po_line_id) REFERENCES ap.purchase_order_line(po_line_id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_invoice_line_po_line
    ON ap.invoice_line (po_line_id);
