-- Corrects ap.purchase_category_tds_mapping's default payment-nature
-- suggestions to match this environment's REAL purchase_category codes.
--
-- migration_tds_foundation.sql's original seed guessed at category codes
-- (PROF_SERV, FAC_ADMIN, IT_TECH, etc.) that turned out not to match what's
-- actually on this environment (IT_HARDWARE, IT_SOFTWARE, FIN_AUDIT,
-- FIN_ACCOUNTING, ADMIN_OFFICE, ADMIN_FACILITIES, TEST_CAT_ONE) - only
-- IT_HARDWARE happened to coincide, so every other category silently fell
-- through to the ELSE branch (OTHER, which has no TDS_RATE rule configured -
-- i.e. TDS never gets suggested for those categories at all).
--
-- Confirmed with the business before applying (2026-09-25):
--   IT_SOFTWARE     -> PROFESSIONAL_SERVICE
--   ADMIN_OFFICE    -> PURCHASE_OF_GOODS
--   FIN_AUDIT / FIN_ACCOUNTING -> left as OTHER for now (NOT confirmed -
--     do not map these without a separate decision)
--   ADMIN_FACILITIES -> left as OTHER for now (explicitly deferred pending
--     confirmation of what these invoices actually are - contract labor vs.
--     rent vs. something else; do not guess)
--
-- Repoints the EXISTING default mapping row's tds_payment_nature_id rather
-- than inserting a second row for the same category - the app's lookup
-- (PurchaseCategoryTdsMapping WHERE is_default=true) takes the lowest-id
-- match, so a second is_default=true row for the same category would leave
-- the old one silently winning instead of being replaced.
--
-- Safe to re-run: updating to the same value twice is a no-op.

UPDATE ap.purchase_category_tds_mapping m
SET tds_payment_nature_id = tpn.id, updated_at = CURRENT_TIMESTAMP
FROM ap.purchase_category pc, ap.tds_payment_nature tpn
WHERE m.purchase_category_id = pc.id
  AND pc.code = 'IT_SOFTWARE'
  AND tpn.code = 'PROFESSIONAL_SERVICE'
  AND m.is_default = TRUE;

UPDATE ap.purchase_category_tds_mapping m
SET tds_payment_nature_id = tpn.id, updated_at = CURRENT_TIMESTAMP
FROM ap.purchase_category pc, ap.tds_payment_nature tpn
WHERE m.purchase_category_id = pc.id
  AND pc.code = 'ADMIN_OFFICE'
  AND tpn.code = 'PURCHASE_OF_GOODS'
  AND m.is_default = TRUE;

-- Verification:
--   SELECT pc.code, tpn.code FROM ap.purchase_category_tds_mapping m
--   JOIN ap.purchase_category pc ON pc.id = m.purchase_category_id
--   JOIN ap.tds_payment_nature tpn ON tpn.id = m.tds_payment_nature_id
--   ORDER BY pc.code;
--   -- expect: IT_HARDWARE->PURCHASE_OF_GOODS, IT_SOFTWARE->PROFESSIONAL_SERVICE,
--   --         ADMIN_OFFICE->PURCHASE_OF_GOODS, everything else unchanged (->OTHER)
