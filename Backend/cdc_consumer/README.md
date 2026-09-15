# CDC Consumer

Keeps `ap.approver_directory` / `ap.approver_directory_role` (and their
supporting lookup caches) in sync with two upstream systems — **UMS**
(MySQL) and **EOS** — via Kafka CDC events. It never queries UMS/EOS
directly; everything arrives as Debezium change events on Kafka topics.

```
MySQL (UMS) ──Debezium──▶ Kafka topics ──▶ this consumer ──▶ Postgres (ap.*)
EOS DB      ──Debezium──▶ Kafka topics ──┘
```

## Running it

Separate process from the API, not started by `uvicorn Backend.main:app`:

```
python -m Backend.cdc_consumer.run_consumer
```

Config comes entirely from environment variables — see the
`KAFKA_*`/`CDC_*` block in `Backend/.env.example`.

## Files

**This package:**

| File | Role |
|---|---|
| `run_consumer.py` | Entrypoint. Creates tables if missing, starts the retry-scheduler thread, runs the Kafka poll loop on the main thread, handles SIGINT/SIGTERM for graceful shutdown. |
| `consumer.py` | The Kafka poll loop: parse → apply → commit offset. On failure, logs to `ap.cdc_failure_log` and commits the offset anyway (a poison message must never wedge the partition) — the retry scheduler picks it up later. |
| `cdc_event.py` | Parses a raw Debezium envelope (`{before, after, source, op, ts_ms}`) into a normalized `CdcEvent`. |
| `retry_scheduler.py` | Background thread that replays retryable `ap.cdc_failure_log` rows every `CDC_RETRY_INTERVAL_SECONDS`, up to `CDC_MAX_RETRIES` attempts each. |

**Elsewhere, but part of the same pipeline** (shared between the live
consumer and the retry scheduler, so sync logic is never duplicated):

| File | Role |
|---|---|
| `Backend/Business_Layer/services/cdc_sync_service.py` | All the actual sync logic — one `process_*_event` function per entity type (department, employee, user, role, user_role). Both `consumer.py` and `cdc_retry_service.py` call these same functions. |
| `Backend/Business_Layer/services/cdc_retry_service.py` | Replays failures found by the scheduler, reusing `cdc_sync_service`. |
| `Backend/Business_Layer/services/cdc_failure_log_service.py` | Reads/writes `ap.cdc_failure_log` rows. |
| `Backend/Business_Layer/utils/cdc_exceptions.py` | `MalformedCdcEventError` (not retryable — bad data), `MissingDependencyError` (retryable — a cross-topic dependency hasn't synced yet), `UnknownCdcTopicError`. |
| `Backend/Data_Access_Layer/dao/cdc_dao.py` | All DB reads/writes for the cache and directory tables. |
| `Backend/Data_Access_Layer/models/cdc.py` | SQLAlchemy models: `ApproverDirectory`, `ApproverDirectoryRole`, `EosDepartmentCache`, `EosEmployeeCache`, `UmsUserCache`, `UmsRoleCache`, `CdcFailureLog`. |
| `Backend/config/kafka_config.py` | Reads `KAFKA_*`/`CDC_*` env vars into a `KafkaConfig`. |

## How events resolve

- `ums.user` / `ums.role` populate small AP-owned lookup caches
  (`ums_user_cache`: `user_id → user_uuid`, `ums_role_cache`:
  `role_id → role_name`) — needed because `ums.user_role` events only
  carry the numeric IDs, not the UUID/name `approver_directory_role`
  actually stores.
- `eos.employee_details` / `eos.departments` populate `eos_employee_cache`
  / `eos_department_cache`. **Confirmed**: `employee_details.employee_uuid`
  is always the same value as `ums.user.user_uuid` — that's the real
  link between the two systems, not a guess.
- A `ums.user` event only produces an `approver_directory` row once the
  matching EOS employee *and* department have synced — if not yet, it's
  logged as a retryable `MissingDependencyError`, not dropped.
- Two exceptions — `SYSTEM_USER_IDS` in `cdc_sync_service.py`, currently
  `{1, 2}` — are UMS system/admin accounts with no real EOS employee
  record (no offer letter, no department). They sync straight into
  `approver_directory` with `department_uuid = NULL`, meaning "applies to
  every department," instead of going through the EOS lookup.
- Every delete is resolved the same way as a create — if the row it
  needs to look up isn't cached yet, it's retried, never silently
  dropped as "already satisfied." A delete that appears to have nothing
  to remove is not proof the goal is met; it may just not be resolvable
  yet.

## Failure handling

Every failure is one row in `ap.cdc_failure_log` (`status`: `FAILED` →
`RETRYING` → `RESOLVED` or `EXHAUSTED` after `CDC_MAX_RETRIES` attempts).
`EXHAUSTED` rows are not retried automatically — if the underlying data
gap gets fixed later (e.g. EOS finally publishes a missing employee), the
row needs `status` reset back to `FAILED` (and `retry_count` to `0`) to be
picked up again.
