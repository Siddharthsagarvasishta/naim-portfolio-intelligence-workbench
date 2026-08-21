# Durable workflow persistence

nAIM keeps analytical datasets in Parquet/DuckDB and mutable business workflow state in a separate transactional database.

## Profiles

- Local default: SQLite at `data/state/naim_workflow.sqlite3`.
- Production-style option: set `NAIM_DATABASE_URL` to a PostgreSQL SQLAlchemy URL and install the PostgreSQL driver from the production extra.
- Schema management: Alembic revision `20260801_0001` creates the initial state, version, audit, user, and revoked-token tables.

Apply migrations with:

```text
.venv/bin/alembic upgrade head
```

## Governed object types

The shared workflow store supports investigations, investigation notes, basket definitions, basket-membership versions, workspaces, workspace versions, approvals, commentary records, export jobs, scenario runs, rating methodologies, and configuration changes.

Each object has:

- a stable external identifier;
- current materialized JSON state;
- an integer version;
- created/modified timestamps and actors;
- an approval state;
- soft-deletion metadata;
- immutable append-only versions;
- hash-chained audit events.

Updates require the caller's expected version. A stale update fails with a concurrency conflict instead of overwriting newer work. Soft-deleted records remain available only through explicit history/audit paths.

## Restart behavior

File-backed SQLite tests create all required object types, dispose the first database engine, construct a new store, and verify that every object is still present. Separate tests cover optimistic concurrency, approvals, version history, soft deletion, and audit-chain verification.

## Security boundary

The workflow database must not hold raw portfolio source files or hidden synthetic ground truth. It stores governed state and identity metadata. Secrets and plaintext passwords are prohibited; demonstration authentication stores only modern password hashes and revocation records.
