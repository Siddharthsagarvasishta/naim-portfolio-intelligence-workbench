# Local lifecycle and database recovery

nAIM runs locally without Docker and without a paid service. After dependencies are installed,
the normal operator path is:

```bash
make start
```

This command checks Python and Node, verifies or safely repairs the workflow database, confirms a
validated dataset exists, starts the API and web application in the background, waits for both
health checks, then warms and validates the first governed Command Centre response before it
reports the workbench as ready. The warm-up must contain KPI results, PASS data quality, publication
approval, and matching run/configuration/dataset provenance; a timeout or mismatch stops both owned
services instead of exposing a cold page. Startup then records process IDs and opens
`http://localhost:3000`. API documentation is deliberately exposed at
`http://localhost:8000/api/docs`.

The generated lifecycle state and logs live below `work/local/`, which is excluded from release
archives. Docker remains available only through the optional `make run-docker` path.

## Operator commands

```bash
make start             # start both local services and open the browser
make stop              # stop only the recorded nAIM process groups
make restart           # safe stop, port release check, start and reopen
make status            # processes, PIDs, ports, health, profile, data and database
make open              # open the already-healthy frontend
make logs              # show the latest API and frontend log lines
```

The aliases `make naim-start`, `make naim-stop`, and `make naim-restart` are equivalent. For
headless validation, set `NO_OPEN=1`; change the log tail with `LOG_LINES=200`. Ports and profile
can be selected with `API_PORT`, `FRONTEND_PORT`, and `PROFILE`.

The stop path never searches for arbitrary Python or Node processes. It uses the recorded PID,
checks the expected command identity and process group, signals only that owned group, removes the
stale record, and checks that the recorded port is released. An occupied unrecorded port blocks
startup instead of being killed.

## Database status and repair

```bash
make db-status
make db-repair
make db-upgrade
```

`db-status` is diagnostic and reports the selected database path, integrity check, application
tables, current and head revisions, exact table/column/index/unique-key/foreign-key differences,
and whether `NAIM_DATABASE_URL` agrees with the `NAIM_DATA_DIR` default.

`db-upgrade` is appropriate for an empty database or a correctly versioned database. It refuses a
compatible-but-unstamped, partially migrated, unknown-revision, or incompatible schema and directs
the operator to the guarded repair command.

`db-repair` always creates a timestamped backup when the SQLite file exists. It then:

1. runs SQLite integrity checks;
2. compares every expected workflow table, ordered column and type, nullability and primary key;
3. compares named indexes and unique constraints plus foreign-key targets and delete behavior;
4. stamps revision `20260801_0001` only when the existing schema matches exactly;
5. upgrades to the current Alembic head and inspects the result again.

An incompatible or ambiguously stamped database is backed up and left unchanged. The command
prints the mismatches and a manual recovery sequence; it never deletes or rebuilds the selected
file automatically.

File-backed `WorkflowStore` startup now uses this same migration bootstrap. Direct SQLAlchemy
`create_all` remains only for isolated in-memory test databases, where a separate Alembic
connection cannot address the same ephemeral store.

## Convenience-target truthfulness

`make self-test`, `make typecheck`, `make export-tableau`, `make export-sas`,
`make export-linkedin`, and `make release-check` are wired to executable checks or generators.
`make release-check` fails closed when cross-artifact reconciliation is incomplete.

The requested `make demo-60` and `make export-powerpoint` names are present but deliberately fail
with an explanatory message until their standalone governed runners exist. They do not substitute
a different demo or claim that an old presentation was regenerated.
