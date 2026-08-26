-- Migration: Add structured header fields to purchase_order/goods_receipt
-- and introduce purchase_order_line / goods_receipt_line for line-item
-- data. Same fields serve manual entry today and a future OCR pipeline —
-- no separate manual-data/OCR-data tables.
--
-- Context: this project has no migration tool (no Alembic) — schema is
-- hand-maintained in Database/ap_schema.sql and applied via
-- Base.metadata.create_all() at app startup, which only creates missing
-- tables and never ALTERs existing ones. This file must be run manually
-- against the target database; ap_schema.sql has been updated to match
-- the resulting shape for any future fresh deployment.
--
-- Additive and idempotent: safe to run against a database that already
-- has these columns/tables/indexes.

BEGIN;

ALTER TABLE ap.purchase_order
    ADD COLUMN IF NOT EXISTS po_date                DATE,
    ADD COLUMN IF NOT EXISTS expected_delivery_date  DATE,
    ADD COLUMN IF NOT EXISTS currency_id             INT,
    ADD COLUMN IF NOT EXISTS subtotal                NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS tax_amount              NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS total_amount            NUMERIC(18,2);

ALTER TABLE ap.purchase_order
    DROP CONSTRAINT IF EXISTS purchase_order_currency_id_fkey;

ALTER TABLE ap.purchase_order
    ADD CONSTRAINT purchase_order_currency_id_fkey
        FOREIGN KEY (currency_id)
        REFERENCES ap.currency(currency_id);

ALTER TABLE ap.goods_receipt
    ADD COLUMN IF NOT EXISTS grn_number    VARCHAR(50),
    ADD COLUMN IF NOT EXISTS receipt_date  DATE;

CREATE TABLE IF NOT EXISTS ap.purchase_order_line (
    po_line_id   SERIAL PRIMARY KEY,
    po_id        INT NOT NULL REFERENCES ap.purchase_order(po_id) ON DELETE CASCADE,
    item_code    VARCHAR(50),
    description  VARCHAR(255) NOT NULL,
    quantity     NUMERIC(18,4) NOT NULL DEFAULT 1,
    unit_price   NUMERIC(18,4) NOT NULL,
    tax_amount   NUMERIC(18,2) NOT NULL DEFAULT 0,
    line_amount  NUMERIC(18,2) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_po_line_po ON ap.purchase_order_line(po_id);

-- po_line_id is SET NULL (not CASCADE) on delete: a PO line being removed
-- should not destroy the goods-receipt record of what physically arrived.
CREATE TABLE IF NOT EXISTS ap.goods_receipt_line (
    grn_line_id       SERIAL PRIMARY KEY,
    grn_id            INT NOT NULL REFERENCES ap.goods_receipt(grn_id) ON DELETE CASCADE,
    po_line_id        INT REFERENCES ap.purchase_order_line(po_line_id) ON DELETE SET NULL,
    item_code         VARCHAR(50),
    description       VARCHAR(255) NOT NULL,
    received_quantity NUMERIC(18,4) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_grn_line_grn ON ap.goods_receipt_line(grn_id);
CREATE INDEX IF NOT EXISTS idx_grn_line_po_line ON ap.goods_receipt_line(po_line_id);

COMMIT;
