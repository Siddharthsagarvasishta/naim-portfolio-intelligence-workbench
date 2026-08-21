# Cross-artifact reconciliation

## Purpose

`scripts/reconcile_release_artifacts.py` is the release-blocking control for the governed nAIM
story. It compares every current delivery channel with the canonical interoperability snapshot and
verifies the channel's native checksums and provenance. The harness is read-only except for its own
JSON result.

The canonical source is:

```text
exports/validation/interop_evidence_snapshot.json
```

That snapshot is produced from `WorkbenchService(load_config('default'))`, the same service methods
used by the API. The harness verifies the snapshot's canonical payload hash before using any claim.
It also links the snapshot to its run manifest and independently computes the dataset hash over the
validated and mart files.

## Approved control scope

The headline control is the calculated all-portfolio peak:

- reporting period: 2025-08-01;
- comparison period: 2025-07-01;
- metric: `ANNUALISED_NET_LOSS_RATE` version 1.0.0;
- observed movement: 311.4150049234624 basis points;
- mix contribution: 4.433506460154617 basis points;
- within-segment contribution: 306.9814984633076 basis points;
- reconciliation residual: 5.204170427930421e-14 basis points;
- primary dimension and driver: `acquisition_channel` / `Affiliate`;
- causal status: `ASSOCIATIONAL`.

`BASKET-001` is separately verified as the approved account-level control basket. It is an approved
secondary drill-through population, not a claim that the all-portfolio headline was calculated on
that basket.

## Required channels

The report always contains these nine channels, even when an artifact is absent:

1. API/service canonical evidence;
2. browser-validated UI snapshot;
3. Excel workbook;
4. PowerPoint review;
5. Tableau Hyper extract;
6. Power BI validation data;
7. Streamlit runtime snapshot;
8. static share site;
9. LinkedIn social pack and carousel.

This fixed inventory prevents a missing channel from disappearing from the denominator.

## Comparison rules

- Machine-readable numerical claims use an absolute tolerance of `1e-9`.
- The bridge residual uses an absolute tolerance of `1e-8` basis points.
- A presentation or carousel that intentionally displays one decimal place is checked against the
  canonical rounded value, equivalent to a maximum display tolerance of `0.05` basis points.
- Text and categorical claims are exact after the adapter's documented normalization. Causal status,
  the primary driver, data-quality status, metric version, period, run ID and synthetic-data flag are
  not numerically rounded.
- Filter-scope comparison treats spaces, underscores and hyphens as equivalent separators, so the
  machine-readable value `all_portfolio` reconciles to the display label `All portfolio` without
  weakening the required scope claim.
- An evidence-ID brand prefix may change during migration, but the complete source run ID must be
  present. This prevents a cosmetic prefix from breaking lineage while still rejecting an unrelated
  run.
- Every file ledger is rehashed from disk. Paths that escape the declared artifact root, missing
  files, byte-count differences and checksum differences are blockers.
- A native validation marked `PASS` is necessary but not sufficient. The harness independently
  checks the governed story and §112 provenance fields.

## Fail-closed outcomes

Each check has one of five outcomes:

- `PASS`: the required evidence exists and agrees;
- `FAIL`: present evidence contradicts the canonical source or its declared checksum;
- `MISSING`: required evidence is absent;
- `UNVERIFIABLE`: the artifact exists but its required reader or validation could not run;
- `NOT_APPLICABLE`: an explicitly optional check does not apply.

A channel is `FAIL` when any required check fails. It is `INCOMPLETE` when there is no mismatch but a
required check is missing or unverifiable. It is `PASS` only when all required checks pass.

The overall result is:

- `FAIL` if any required check fails;
- otherwise `INCOMPLETE` if any required check is missing or unverifiable;
- otherwise `PASS`.

`release_allowed` is true only for `PASS`. The command exits non-zero for both `FAIL` and
`INCOMPLETE`.

## Provenance contract

For each final XLSX, PPTX, Hyper and HTML file, the corresponding manifest under
`outputs/manifests/` must provide and reconcile:

- artifact or build ID;
- creation time;
- physical file SHA-256;
- dataset hash;
- configuration hash;
- code or builder version;
- metric-registry version;
- reporting period;
- filter scope;
- evidence IDs;
- data-quality result;
- synthetic-data status.

The Power BI project manifest and LinkedIn package manifest must carry the same fields directly,
plus a complete file ledger. A manifest that only lists file hashes is therefore useful but remains
incomplete for release.

Desktop-only outcomes remain separate from portable evidence. A passing static PBIP project does
not claim that Power BI Desktop or Service publication ran; a passing Hyper extract does not claim
that Tableau Desktop or Tableau Cloud publication ran; and SAS compatibility is not a SAS-runtime
result. Missing desktop runtimes must stay explicitly classified rather than being inferred from a
portable package.

## Runtime snapshot schema

The browser and Streamlit controls are captured as JSON at:

```text
outputs/validation/ui_evidence_snapshot.json
outputs/streamlit/evidence_snapshot.json
```

Each snapshot must use this minimal shape:

```json
{
  "schema_version": "1.0.0",
  "channel": "ui",
  "captured_at_utc": "2026-08-01T00:00:00+00:00",
  "source_url": "http://127.0.0.1:3000",
  "source_context": {
    "active_mode": "OFFLINE_SNAPSHOT",
    "run_id": "default-73421-6006e471387a",
    "configuration_hash": "<sha256>",
    "dataset_hash": "<sha256>"
  },
  "governed_story": {
    "reporting_period": "2025-08-01",
    "comparison_period": "2025-07-01",
    "current_annualised_net_loss_rate": 0.06685632988073756,
    "prior_annualised_net_loss_rate": 0.035714829388391336,
    "observed_change_bps": 311.4150049234624,
    "mix_contribution_bps": 4.433506460154617,
    "within_segment_contribution_bps": 306.9814984633076,
    "reconciliation_residual_bps": 5.204170427930421e-14,
    "primary_dimension": "acquisition_channel",
    "primary_driver": "Affiliate",
    "causal_status": "ASSOCIATIONAL",
    "run_id": "default-73421-6006e471387a",
    "metric_registry_version": "1.0.0",
    "data_quality_status": "PASS",
    "synthetic_data": true
  }
}
```

Capturing a JSON response directly from the backend is not sufficient for the UI control. The UI
snapshot must be created from values read from the rendered browser state at the tested viewport.
The same rule applies to the Streamlit runtime.

## Output schema

The result is written to:

```text
outputs/validation/cross_artifact_reconciliation.json
```

Its machine-readable JSON Schema is:

```text
schemas/cross-artifact-reconciliation.schema.json
```

Top-level fields are:

- `schema_version`, `product`, `generated_at_utc`;
- `result` and `release_allowed`;
- `methodology`, including tolerances and scope policy;
- `canonical`, containing source hashes, the exact story and source checks;
- `channels`, with a stable channel ID, status, artifact paths, checks and notes;
- `summary`, with channel counts, failed checks, missing/unverifiable checks and a compact blocker
  list.

Every check records `check_id`, `required`, `outcome`, `expected`, `actual`, and optional
`tolerance`, `evidence`, and `detail`. Evidence paths are repository-relative and portable.
Every existing file named by a channel is also recorded under that channel's `artifacts` array with
its byte size and independently calculated SHA-256, including when its declared ledger is missing.

## Running the control

From the repository root:

```text
PYTHONPATH=src .venv/bin/python scripts/reconcile_release_artifacts.py
```

Rerun the harness only after all final artifact bytes and manifests have been written. Any later
layout, metadata or packaging change invalidates the previous file checksum and requires another
run.
