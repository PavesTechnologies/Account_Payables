-- Seeds CGST/SGST/IGST as distinct tax_type rows for India (country_id=1),
-- alongside the existing combined 'GST18' row. Additive and idempotent
-- (ON CONFLICT on the existing (country_id, tax_code, effective_from)
-- unique constraint) — safe to run against a database that already has
-- them.
--
-- Why: Business_Layer/utils/invoice_process_service._apply_line_tax_types
-- maps each invoice_line's extracted tax label (uppercased, e.g. "CGST",
-- "SGST", "IGST" — see Business_Layer/utils/extraction/line_items.py)
-- directly against tax_type.tax_code for (country_id, tax_code,
-- effective_from). Only a combined 'GST18' code existed before this
-- migration, so any invoice whose line items show a split GST breakdown
-- (the standard format for Indian intra-state GST, e.g. CGST 9% + SGST 9%
-- instead of one 18% line) could never resolve tax_type_id on those lines.
--
-- Rates: CGST 9% + SGST 9% = 18% intra-state; IGST 18% inter-state —
-- matching the existing GST18 combined rate, split per standard GST rules.
-- Not a new/invented rate.

INSERT INTO ap.tax_type
    (country_id, tax_name, tax_code, calculation_type, rate_percent, is_withholding, effective_from, is_system_default, is_active)
VALUES
    (1, 'CGST 9%', 'CGST', 'PERCENTAGE', 9.000, FALSE, '2024-01-01', TRUE, TRUE),
    (1, 'SGST 9%', 'SGST', 'PERCENTAGE', 9.000, FALSE, '2024-01-01', TRUE, TRUE),
    (1, 'IGST 18%', 'IGST', 'PERCENTAGE', 18.000, FALSE, '2024-01-01', TRUE, TRUE)
ON CONFLICT (country_id, tax_code, effective_from) DO NOTHING;
