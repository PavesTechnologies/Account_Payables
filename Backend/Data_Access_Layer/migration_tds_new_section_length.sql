-- Follow-up to migration_tds_configuration.sql: Income-tax Act 2025 section
-- references are longer than 20 characters (e.g. "393(1) Table 6(iii).D(a)",
-- "393(1) Table 7 / Table 4(ii)"). Widening a VARCHAR is non-destructive and
-- safe to re-run. Rollback (only if no value exceeds 20 chars):
--   ALTER TABLE ap.tax_rule ALTER COLUMN new_section TYPE VARCHAR(20);

ALTER TABLE ap.tax_rule ALTER COLUMN new_section TYPE VARCHAR(100);
