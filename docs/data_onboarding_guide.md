# nAIM Data Onboarding Studio

The local Data Onboarding Studio turns a bounded source into a validated canonical preview without writing into active analytical data. Invalid records are quarantined, every load is reconciled, and a saved import profile remains inactive until an explicit approval.

## Supported sources

| Source | Registration | Governed behavior |
| --- | --- | --- |
| CSV | `.csv` upload or selection | UTF-8/UTF-8-BOM, parser errors rejected |
| Excel | `.xlsx` upload or selection | External links and formula cells rejected; one named or indexed sheet |
| Parquet | `.parquet` upload or selection | Metadata row/column limits checked before materialization |
| JSON | `.json` upload or selection | JSON records array or newline-delimited records |
| SQLite | `.sqlite`, `.sqlite3`, or `.db` | Read-only connection; base tables only; no caller-supplied SQL |
| DuckDB | `.duckdb` | Read-only connection, external access disabled, base tables only |
| PostgreSQL | environment-referenced connection URL | Base tables only; the URL itself is never included in a response, profile, artifact, or audit state |

Uploads and selections stay below the configured byte, row, column, preview, and error-preview limits. A local path must resolve under `<onboarding_root>/sources`, cannot contain `..`, and cannot be a symbolic link. Registered files are content-hashed and rechecked before every use.

The default application integration should use `data/onboarding` as the onboarding root and inject the application's durable `WorkflowStore` into `OnboardingStudio`. PostgreSQL execution also requires an installed SQLAlchemy PostgreSQL driver such as `psycopg`; connection URLs should use an environment variable such as `NAIM_ONBOARDING_POSTGRES_URL`.

## Canonical contracts

`OnboardingStudio.contracts()` exposes versioned field definitions and unique keys for exactly eight contracts:

1. `account_master`
2. `account_month_performance`
3. `strategy_decision`
4. `partner_performance`
5. `vendor_performance`
6. `membership_history`
7. `benefit_usage`
8. `economic_assumptions`

Required fields, primitive types, non-negative measures, unique keys, and applicable effective-date ordering are validated. Contract version `1.0.0` is captured in every profile and run.

## Safe formulas

Derived fields use `SafeFormula`, a small AST interpreter. Python `eval`, `exec`, imports, attributes, subscripting, comprehensions, lambdas, file access, network access, and shell calls are unavailable.

Allowed syntax:

- column names that are valid identifiers;
- numbers, strings, booleans, `None`, bounded list/tuple/dictionary literals;
- `+`, `-`, `*`, `/`, `%`, and `**` arithmetic;
- comparisons, `and`, `or`, and `not`;
- `coalesce(a, b, ...)`;
- `if_else(condition, when_true, when_false)`;
- `map_value(value, mapping, default)` or `category_map(...)`;
- `clip(value, lower, upper)`;
- `normalize(value)` for Unicode normalization, trim, whitespace collapse, and case folding;
- `date_diff('days'|'months'|'years', start, end)`.

Division by zero, non-finite arithmetic, and null arithmetic produce a null result. Invalid dates, unsupported units, or unsafe syntax produce controlled formula errors. If a source column contains spaces or punctuation, map it directly to a canonical field or normalize the source header before using it in a derived expression.

## Workflow and persisted outputs

1. Register an upload with `upload_source`, select a governed file with `select_source`, or create a secret-free PostgreSQL descriptor with `configure_postgresql_source`.
2. For a database source, list base tables with `list_database_tables` and bind one with `with_table`.
3. Call `preview_source` to sample rows and infer types.
4. Select one canonical contract.
5. Call `validate_mapping` with direct field mappings and optional safe transformations.
6. Call `validate_source` to see the pass/fail result and bounded valid/error previews.
7. Call `save_import_profile`. The profile is persisted as a versioned `configuration_change` in `WorkflowStore` and mirrored as portable JSON.
8. Call `run_import_profile` (or `load_into_onboarding_namespace`) with the profile and a compatible source.
9. Inspect the namespace, quarantine, preview mart, hashes, and source-to-output reconciliation.
10. Call `approve_profile` with the latest profile version and a rationale. Approval fails unless the latest run passed its configured error threshold and reconciled.

The run writes only beneath the onboarding root:

```text
sources/<source_id>/...
profiles/<profile_id>.json
namespace/<profile_id>/<run_id>/data.parquet
quarantine/<profile_id>/<run_id>/invalid_rows.parquet
preview_marts/<profile_id>/<run_id>/summary.parquet
preview_marts/<profile_id>/<run_id>/run.json
```

All paths returned to clients are relative to the onboarding root. The namespace contains valid canonical rows. The quarantine contains invalid canonical rows plus `_source_row_number` and `_error_codes`. The long-form preview mart contains row counts, error rate, and numeric source/loaded/quarantine totals. Reconciliation proves:

`source rows = loaded rows + quarantined rows`

and applies a scale-aware tolerance to every canonical numeric total. A run never writes into active analytics (`loaded_to_active_analytics` is always `false`). Approval activates the reusable profile, not an automatic production-data promotion.

## Callable facade payloads

The following schemas are the intended API integration contract. Unknown fields should be rejected by the API's request models.

### Source descriptor

Local source:

```json
{
  "source_id": "generated-id",
  "kind": "csv|xlsx|parquet|json|sqlite|duckdb",
  "display_name": "accounts.csv",
  "relative_path": "sources/generated-id/accounts.csv",
  "size_bytes": 1234,
  "sha256": "64-lowercase-hex",
  "table": "optional_base_table",
  "sheet": "optional-sheet-name-or-index"
}
```

PostgreSQL source:

```json
{
  "source_id": "generated-id",
  "kind": "postgresql",
  "display_name": "PostgreSQL:public.accounts",
  "url_env": "NAIM_ONBOARDING_POSTGRES_URL",
  "table": "public.accounts"
}
```

Never accept or return an inline PostgreSQL URL.

### Preview

Facade call:

```python
studio.preview_source(source, sample_rows=50)
```

Suggested `POST /api/v1/data-onboarding/preview` body:

```json
{"source": {"...": "source descriptor"}, "sample_rows": 50}
```

Response keys: `source`, `sample_row_count`, `sample_limit`, `columns`, `rows`, and `suggested_mappings`. Each column contains `name`, `inferred_type`, `confidence`, `null_count_in_sample`, and `distinct_count_in_sample`.

### Map

Facade call:

```python
studio.validate_mapping(
    source,
    contract_id="account_master",
    mapping={"account_id": "acct_id"},
    transformations={"region": "normalize(raw_region)"},
)
```

Suggested `POST /api/v1/data-onboarding/map` body:

```json
{
  "source": {"...": "source descriptor"},
  "contract_id": "account_master",
  "mapping": {"account_id": "acct_id"},
  "transformations": {"region": "normalize(raw_region)"}
}
```

Response keys: `valid`, `contract_id`, `contract_version`, `mapped_fields`, `derived_fields`, and `source_fields_used`.

### Validate

Facade call:

```python
studio.validate_source(
    source,
    contract_id="account_master",
    mapping={"account_id": "acct_id"},
    transformations={},
    max_error_rate=0.0,
)
```

Suggested `POST /api/v1/data-onboarding/validate` body:

```json
{
  "source": {"...": "source descriptor"},
  "contract_id": "account_master",
  "mapping": {"account_id": "acct_id"},
  "transformations": {},
  "max_error_rate": 0.0
}
```

Response keys: `source`, `validation`, `error_preview`, `valid_row_preview`, and `invalid_row_preview`. `validation` contains `source_rows`, `valid_rows`, `invalid_rows`, `validation_error_count`, `error_rate`, `max_error_rate`, and `passed`.

### Save profile

Facade call:

```python
studio.save_import_profile(
    "account-master-v1",
    source,
    contract_id="account_master",
    mapping={"account_id": "acct_id"},
    transformations={},
    max_error_rate=0.0,
    actor=principal.username,
)
```

Suggested `POST /api/v1/data-onboarding/profiles` body:

```json
{
  "profile_id": "account-master-v1",
  "source": {"...": "source descriptor"},
  "contract_id": "account_master",
  "mapping": {"account_id": "acct_id"},
  "transformations": {},
  "max_error_rate": 0.0
}
```

The authenticated principal supplies `actor`; clients must not select an audit actor. The response contains the saved mapping, contract version, required source columns, draft validation, `version: 1`, `approval_state: DRAFT`, `active: false`, and a bounded error preview.

### Load and reconcile

Facade call:

```python
studio.load_into_onboarding_namespace(
    "account-master-v1",
    source,
    actor=principal.username,
    expected_version=1,
)
```

Suggested `POST /api/v1/data-onboarding/load` body:

```json
{
  "profile_id": "account-master-v1",
  "source": {"...": "source descriptor"},
  "expected_version": 1
}
```

Response keys: `run_id`, `profile_id`, `profile_version`, `profile_approval_state`, `profile_active`, `contract_id`, `contract_version`, `source`, `validation`, `error_preview`, `reconciliation`, `outputs`, `output_hashes`, `loaded_to_active_analytics`, `ran_at_utc`, and `actor`.

### Approve

Facade call:

```python
studio.approve_profile(
    "account-master-v1",
    expected_version=2,
    actor=principal.username,
    rationale="Validation passed and source totals reconcile.",
)
```

Suggested `POST /api/v1/data-onboarding/profiles/{profile_id}/approve` body:

```json
{
  "expected_version": 2,
  "rationale": "Validation passed and source totals reconcile."
}
```

The response is the current profile with `approval_state: APPROVED`, `active: true`, the approval actor/rationale/timestamp, and an incremented version. Stale versions produce a concurrency conflict; validation or reconciliation failures produce an approval conflict.

## Operational checks

- Keep `max_upload_bytes`, `max_rows`, and `max_columns` conservative for the deployment.
- Mount the onboarding root on durable storage when the API runs in a container.
- Authorize source registration, profile creation, loading, and approval separately at the endpoint layer.
- Treat PostgreSQL environment configuration as an administrator operation.
- Retain `run.json`, Parquet hashes, profile versions, and `WorkflowStore` audit events together for evidence.
- Do not promote `namespace` files into active analytics without a separate governed publishing workflow.
