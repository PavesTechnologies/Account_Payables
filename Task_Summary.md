Date: 22/07/2026
task summary for master related data

Summary of what was built, following your decisions:

Business config tier (new, under /apm/master):

master_interface.py, master_route.py, master_service.py, master_dao.py
tax_type — full CRUD; create/update validate country_id FK exists and enforce the calculation_type/rate_percent/fixed_amount check-constraint logic and effective_from/effective_to ordering before hitting the DB; delete blocked with 409 when is_system_default=true.
payment_term — full CRUD; same system-default delete guard.
system_configuration — read + value/description update only (no create/delete), with a validator that checks config_value parses against the row's locked data_type.
New utils: tax_type_validator.py, system_config_validator.py.
System reference tier (extended existing system files, still under /apm/system):

status_master — read-only list/get plus a label-only update (status_name/display_order); status_code/module_name are never exposed for create/edit/delete, per the README's "codes are locked" rule.
Skipped: vendor_category, since its table is commented out in ap_schema.sql and doesn't exist in the DB.

Verified: all files byte-compile, main.py imports and boots against the live DB (Base.metadata.create_all succeeded), and the OpenAPI schema confirms all 12 new routes are registered correctly alongside the existing country/currency ones.