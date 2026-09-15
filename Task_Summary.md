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

CDC Implementation Summary
Prior build (files dated 2026-09-09, before this session — I have no direct record of that work, only what the code shows): The Backend/cdc_consumer/ package, cdc_sync_service.py, cdc_dao.py, cdc.py models, cdc_exceptions.py, and kafka_config.py were already in place, implementing the Kafka→Postgres sync pipeline for ums.user/role/user_role and eos.employee_details/departments into ap.approver_directory/approver_directory_role. Several design assumptions in that build were unconfirmed (documented in its own comments as "not yet confirmed against a real sample").

Today (2026-09-15), this session:

Found and fixed 3 bugs causing the sync to silently fail:

A transaction-scoping bug where a user's user_id→user_uuid cache write got rolled back alongside unrelated EOS-dependency failures, so users could never get cached no matter how many retries ran — the root cause of most cascading failures.
A bad assumption that a legacy employee_id payload field was always a UUID — crashed permanently instead of falling back gracefully.
Delete events for an unresolved user were silently treated as "already done" instead of retried — caused real, silent data loss (confirmed one concrete case: a stale Project_Manager role that should've been deleted).
Result: 119 of 133 backlogged failures self-resolved after the fixes.
Confirmed the real UMS↔EOS link: eos.employee_details.employee_uuid is always identical to ums.user.user_uuid — validated against a live EOS data sample, not just inferred.

Designed and implemented handling for non-onboarded UMS accounts (user_id 1 "Paves Admin", 2 "System Internal" — not real EOS employees): made approver_directory.department_uuid nullable (migration applied), added SYSTEM_USER_IDS special-case in cdc_sync_service.py so these two sync with department_uuid=NULL ("applies to all departments") instead of requiring a fabricated EOS/offer-letter record.

Manual data reconciliation: cross-referenced live UMS dumps against ap.approver_directory_role for every user — found and fixed exactly one stale-row case (user 5100031, roles 7 and 30, leftover from the swallowed-delete bug before it was fixed); confirmed no other user was affected.

Full model-vs-live-DB audit (all 44 tables in the ap schema): fixed every mismatch found — added 2 missing UNIQUE constraints to the ApproverDirectory/ApproverDirectoryRole models (matching what the DB already had), corrected 2 column-type mismatches, added 2 missing constraints to the live DB (tax_type, vendor_tax, verified no data conflicts first), and added models for 2 previously-unmapped tables (vendor_category, vendor_category_mapping — currently unused by any code, worth a call on whether to drop or wire up).

Repo cleanup: replaced Database/migrations/ + stale ap_schema*.sql with a live-pg_dump-generated schema.sql + dated data_2026-09-15.sql; removed CDC test files and the manual test-event-producer script; wrote Backend/cdc_consumer/README.md; removed all Docker files (Dockerfile, both docker-compose.ymls, .dockerignore) per your instruction, cleaning up the resulting dangling references in run_consumer.py and docker-compose.local-kafka.yml before it was deleted.