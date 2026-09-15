# Database

Two files, both generated from the live `ap` schema via `pg_dump` — not
hand-maintained, so they can't drift from what SQLAlchemy sees:

- **`schema.sql`** — current structure only (tables, constraints, indexes,
  functions/triggers). Regenerate and overwrite this file whenever the live
  schema changes; there is no migration history to keep in sync with it.
- **`data_<date>.sql`** — a dated snapshot of current row data as
  `INSERT` statements. Each snapshot is its own file (don't overwrite an
  older one) — treat it as a point-in-time backup, not a running log.

Both are plain SQL, safe to run through `psql` or pgAdmin's Query Tool.

## Regenerating

```
pg_dump "<DATABASE_URL, postgresql:// not postgresql+psycopg2://>" \
  --schema-only --schema=ap --no-owner --no-privileges -f Database/schema.sql

pg_dump "<DATABASE_URL>" \
  --data-only --column-inserts --schema=ap --no-owner --no-privileges \
  -f Database/data_<today's date>.sql
```

`DATABASE_URL` is in `Backend/.env`. pg_dump 18+ adds `\restrict`/`\unrestrict`
lines at the top/bottom of its output — those are `psql`-only meta-commands,
not valid SQL, and break a plain `psql -f` run or pgAdmin's Query Tool on
older clients. Delete both lines after regenerating.

## Source of truth

The live database is authoritative. `Backend/Data_Access_Layer/models/*.py`
(SQLAlchemy) should match it exactly — verified 2026-09-15 by introspecting
the live DB and comparing every table/column/constraint against the models;
mismatches found were fixed on whichever side was wrong (a few models were
missing constraints the DB already had; a few DB constraints the models
correctly expected were missing and got added, after confirming no existing
data would violate them).

Two tables currently have models but no code anywhere queries them:
`vendor_category` and `vendor_category_mapping`. They're real, well-formed
tables (proper FKs/constraints, same conventions as everything else) — just
unused today. Worth a call on whether they're dead weight to drop or a
feature not yet wired up.
