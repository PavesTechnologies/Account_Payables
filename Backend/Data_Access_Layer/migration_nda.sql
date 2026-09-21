-- Manual migration for the NDA module (Stage 2).
--
-- This codebase has no migration tool (Base.metadata.create_all only creates
-- missing tables and never alters existing ones), so:
--   * ap.nda_template and ap.vendor_nda are NEW tables -> created
--     automatically by create_all() the next time the app starts (models
--     registered in Data_Access_Layer/models/__init__.py).
--   * The status_master rows, system_configuration rows and the seed template
--     below must be applied by hand, the same way every other status_master
--     row in this app already is (see migration_rfq_workflow.sql).
--
-- Stage 1 tables are NOT touched. No existing row is updated or deleted.
-- Safe to re-run: every statement is ON CONFLICT DO NOTHING.

-- ---------------------------------------------------------------
-- 1) NDA document lifecycle statuses.
--
-- ap.vendor_nda.nda_status_id is a FK to status_master.status_id (the real
-- primary key - there is no status_master.id). Application code resolves
-- these by (module_name, status_code) only, so the ids assigned here are
-- irrelevant and are never referenced in code.
-- ---------------------------------------------------------------
INSERT INTO ap.status_master (module_name, status_code, status_name, display_order) VALUES
    ('NDA', 'NOT_REQUIRED', 'Not Required', 10),
    ('NDA', 'PENDING',      'Pending',      20),
    ('NDA', 'SENT',         'Sent',         30),
    ('NDA', 'SIGNED',       'Signed',       40),
    ('NDA', 'COMPLETED',    'Completed',    50),
    ('NDA', 'REJECTED',     'Rejected',     60),
    ('NDA', 'EXPIRED',      'Expired',      70)
ON CONFLICT (module_name, status_code) DO NOTHING;

-- ---------------------------------------------------------------
-- 2) NDA configuration (admin-tunable, follows the existing
--    ap.system_configuration conventions: BOOLEAN stored as 'TRUE'/'FALSE').
--
-- NDA_SIGNED_IS_FINAL=FALSE means an NDA in SIGNED state does NOT satisfy RFQ
-- eligibility - COMPLETED is required. Set it to TRUE only if your process
-- treats SIGNED as the final accepted state.
-- ---------------------------------------------------------------
INSERT INTO ap.system_configuration (config_key, config_value, data_type, description) VALUES
    ('NDA_SIGNED_IS_FINAL', 'FALSE', 'BOOLEAN',
     'Whether an NDA in SIGNED state satisfies RFQ eligibility instead of requiring COMPLETED'),
    ('NDA_VALIDITY_MONTHS', '24', 'NUMBER',
     'Months an NDA remains valid from its completion date before it is treated as expired'),
    ('NDA_TEMPLATE_CODE', 'STANDARD_NDA', 'STRING',
     'Code of the approved ap.nda_template used when generating a vendor NDA')
ON CONFLICT (config_key) DO NOTHING;

-- ---------------------------------------------------------------
-- 3) Seed NDA template.
--
-- Placeholder wording only - REPLACE THE BODY WITH YOUR LEGALLY APPROVED
-- NDA TEXT BEFORE USE. Only the placeholders below are substituted at
-- generation time; the rest of the body is reproduced verbatim and no clause
-- is ever generated dynamically. Bump `version` whenever the body changes so
-- previously issued NDAs remain traceable to the wording they were built
-- from (vendor_nda.template_version stores it per document).
--
-- Supported placeholders: {{VENDOR_NAME}} {{VENDOR_CODE}} {{PR_NUMBER}}
-- {{DEPARTMENT}} {{PURCHASE_CATEGORY}} {{BUSINESS_REQUIREMENT}}
-- {{COMPANY_NAME}} {{EFFECTIVE_DATE}}
-- ---------------------------------------------------------------
INSERT INTO ap.nda_template (code, name, version, body, is_active, created_by, updated_by) VALUES
(
    'STANDARD_NDA',
    'Standard Vendor Non-Disclosure Agreement',
    '1.0',
    'NON-DISCLOSURE AGREEMENT

This Non-Disclosure Agreement ("Agreement") is entered into on {{EFFECTIVE_DATE}} between {{COMPANY_NAME}} ("Disclosing Party") and {{VENDOR_NAME}} (vendor code {{VENDOR_CODE}}) ("Receiving Party").

1. PURPOSE
The parties wish to explore a business relationship in connection with purchase requisition {{PR_NUMBER}}, raised by the {{DEPARTMENT}} department under the {{PURCHASE_CATEGORY}} purchase category, for the following requirement:
{{BUSINESS_REQUIREMENT}}

2. CONFIDENTIAL INFORMATION
"Confidential Information" means all non-public information disclosed by the Disclosing Party to the Receiving Party, whether orally, in writing or in any other form, including commercial, technical, pricing, procurement and operational information.

3. OBLIGATIONS
The Receiving Party shall keep all Confidential Information strictly confidential, shall not disclose it to any third party without prior written consent, and shall use it solely for the purpose described in Clause 1.

4. EXCLUSIONS
This Agreement does not apply to information that is or becomes publicly available through no fault of the Receiving Party, was lawfully known to the Receiving Party before disclosure, or is required to be disclosed by law or a competent authority.

5. TERM
The obligations in this Agreement survive for the period specified in the governing procurement terms from the date first written above.

6. NO LICENCE
Nothing in this Agreement grants the Receiving Party any right, title, licence or interest in the Confidential Information.

IN WITNESS WHEREOF, the parties have executed this Agreement as of {{EFFECTIVE_DATE}}.

For {{COMPANY_NAME}}                       For {{VENDOR_NAME}}

Name:  ____________________                Name:  ____________________

Title: ____________________                Title: ____________________

Date:  ____________________                Date:  ____________________',
    TRUE,
    'migration',
    'migration'
)
ON CONFLICT (code) DO NOTHING;

-- Verification:
--   SELECT status_code, status_name, display_order FROM ap.status_master
--   WHERE module_name = 'NDA' ORDER BY display_order;              -- expect 7 rows
--
--   SELECT config_key, config_value, data_type FROM ap.system_configuration
--   WHERE config_key LIKE 'NDA%';                                   -- expect 3 rows
--
--   SELECT code, name, version, is_active FROM ap.nda_template;      -- expect 1 row
--
--   SELECT column_name, data_type, is_nullable FROM information_schema.columns
--   WHERE table_schema='ap' AND table_name='vendor_nda' ORDER BY ordinal_position;
