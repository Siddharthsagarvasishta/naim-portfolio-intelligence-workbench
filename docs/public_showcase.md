# Public showcase and companion

nAIM has two deliberately narrow public surfaces: a read-only Streamlit companion and a backend-free
static share site. Both consume the same reduced public evidence contract. Neither surface is a
substitute for the governed workbench.

## Public evidence contract

The builder reads the publication-approved aggregate evidence at
`exports/validation/interop_evidence_snapshot.json`, verifies the synthetic flag, quality gate,
publication decision, August 2025 selection rule and exact decomposition reconciliation, then emits
only the fields required for the public story. It removes historical identity metadata and all raw
record structures. The emitted snapshot is checksummed.

The public contract contains:

- product identity, reporting period, data mode and portable source hashes;
- aggregate loss-rate KPI and monthly trend;
- exact mix/within-segment decomposition and causal boundary;
- two-strategy trade-off fields and approval state;
- optional validated aggregate Market Risk evidence;
- explicit synthetic-data, privacy and decision limitations.

It contains no account/customer identifier, contact detail, credential, mutable workflow state or
administrative setting.

## Streamlit companion

`apps/streamlit_demo/streamlit_app.py` defaults to `OFFLINE_SNAPSHOT`. It verifies the companion
checksum and public validation controls before rendering. `API` mode reads one unauthenticated,
public-safe `/api/v1/public-evidence` endpoint. An API error produces `UNAVAILABLE`; the application
does not silently substitute offline or demo data.

The sidebar always shows active mode, health and source. The companion is read-only and provides no
configuration forms, write actions, credential entry or raw-record view. The sample Excel button is
enabled only when the validated canonical workbook exists.

## Market Risk rule

The builder optionally reads `outputs/market_risk/evidence_snapshot.json`. It publishes a reduced
summary only when the snapshot:

- reports implemented analytical status;
- has PASS/publication-allowed validation;
- is synthetic or explicitly redistribution-permitted;
- rules out a trading recommendation and causal claim;
- contains the required volatility, VaR and model-comparison evidence.

If any condition fails or the file is absent, both public surfaces show `UNAVAILABLE — validation
pending`. They never calculate a replacement result.

## Static site

Build from the repository root:

```bash
PYTHONPATH=src .venv/bin/python scripts/build_share_site.py
```

Optional `--repository-url` and `--contact` values replace the visible placeholders. The build
includes project overview, architecture, 60-second story, previews, methodology, a pre-rendered
aggregate chart, public downloads, technology stack, limitations and the synthetic-data statement.
It requires no backend or third-party JavaScript.

The builder validates internal links, output containment, portable paths and common secret patterns.
Results are recorded in `outputs/share_site/validation.json` and `build_manifest.json`.

## Deployment boundary

`.github/workflows/share-site.yml` is manual-only. Its default action builds and retains a reviewable
artifact without publication. A user must explicitly set `publish=true` to invoke the GitHub Pages
deployment job. No LinkedIn publishing automation is configured.

## Verification

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/test_public_showcase.py
.venv/bin/python -m ruff check apps/streamlit_demo scripts/build_share_site.py tests/unit/test_public_showcase.py
```

The smoke test imports and renders the Streamlit structure with an offline fake UI, so it never
requires a backend, browser, or Streamlit server.
