-- Follow-up migration: GST registration compliance signal on ap.invoice_tds.
-- Same hand-applied convention as migration_tds_foundation.sql (this app has
-- no migration tool). Safe to re-run (ADD COLUMN IF NOT EXISTS).
--
-- gstin_status/gstin_checked_at are populated by TDSDeterminationService
-- using the existing Sandbox GSTIN search (Backend/Business_Layer/utils/
-- gst_service.py::search_gstin, wrapped by vendor_auto_onboarding.py's
-- call_gst_search - reused as-is, not duplicated). This is a WARNING/SIGNAL
-- only: it is never read by, and never changes, tds_applicable/tds_rate/
-- tds_amount. A vendor's GST registration status is a GST (indirect-tax)
-- compliance fact, not a TDS (Income-tax withholding) rate input - PAN
-- status (see ap.vendor_tds_profile.pan_status / Section 206AA) remains the
-- only tax-status field that affects the calculated rate.

ALTER TABLE ap.invoice_tds ADD COLUMN IF NOT EXISTS gstin_status VARCHAR(30);
ALTER TABLE ap.invoice_tds ADD COLUMN IF NOT EXISTS gstin_checked_at TIMESTAMP;

-- Verification:
--   SELECT column_name, data_type FROM information_schema.columns
--   WHERE table_schema='ap' AND table_name='invoice_tds'
--   AND column_name IN ('gstin_status', 'gstin_checked_at');   -- expect 2 rows
