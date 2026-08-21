# Power BI source-project enablement

## Honest capability status

`INTEGRATION_ONLY`

The generated package is a statically validated Power BI Project (PBIP) scaffold with a TMDL
semantic model and PBIR report definition. It is not a PBIX and it is not a finished Power BI
report. This repository does not claim Power BI Desktop validation or Power BI Service
publication because neither has been performed in this environment.

Generate or validate the source project from the repository root:

```bash
PYTHONPATH=src .venv/bin/python -m naim_risk.powerbi_project
PYTHONPATH=src .venv/bin/python -m naim_risk.powerbi_project --validate-only
```

The output is `outputs/powerbi/nAIM.PowerBIProject/`.

## Project contents

```text
nAIM.PowerBIProject/
├── nAIM.pbip
├── Report/
│   ├── definition.pbir
│   ├── definition/
│   │   ├── report.json
│   │   ├── version.json
│   │   └── pages/
│   ├── specifications/report-pages.json
│   └── theme/nAIM-theme.json
├── SemanticModel/
│   ├── definition.pbism
│   ├── definition/
│   │   ├── database.tmdl
│   │   ├── model.tmdl
│   │   ├── expressions.tmdl
│   │   ├── relationships.tmdl
│   │   └── tables/*.tmdl
│   ├── measures.dax
│   └── specifications/
│       ├── calculation-group.json
│       └── field-parameters.json
├── Data/*.csv
├── Governance/metric-registry.json
├── Validation/
│   ├── controls.csv
│   └── reconciliation_snapshot.csv
├── Deployment/deployment-checklist.md
└── Build/project-manifest.json
```

The `.pbip` file points to `Report` and `Report/definition.pbir` uses the relative `byPath`
reference `../SemanticModel`. No user-specific absolute path or credential is committed. The
Power Query parameter `nAIMExportRoot` intentionally contains a placeholder and must be set in
Desktop to the project's local `Data` directory.

## Semantic model

The scaffold loads six bounded, synthetic evidence tables:

| Table | Grain | Governed relationship |
|---|---|---|
| `evidence_scope` | one row per evidence run and selected reporting period | shared one-side filter anchor |
| `kpi_snapshot` | governed metric × evidence scope | to `evidence_scope` and `metric_dictionary` |
| `metric_dictionary` | governed metric version | one side of metric relationship |
| `strategy_snapshot` | strategy × evidence scope | to `evidence_scope` only |
| `entity_rating_snapshot` | entity × entity type × evidence scope | to `evidence_scope` only |
| `scenario_snapshot` | scenario × evidence scope | to `evidence_scope` only |

The generator allowlists `kpi_snapshot` rows to metric IDs present in
`config/metric_registry.json`. This prevents convenience metrics without governed definitions
from entering the semantic model. Source and project hashes, the transformation rule, and row
counts are recorded in `Build/project-manifest.json`.

All relationships are many-to-one and single-direction. Independent snapshot facts must never
be joined directly or cross-filtered bidirectionally because that would multiply rows across
different grains. Technical evidence keys are hidden. Dates, booleans, integers, and numeric
columns receive explicit Power Query and TMDL types.

The TMDL contains reviewed DAX measures and explicit format strings for governed rates, basis
points, counts, synthetic currency units, quality controls, strategies, entities, and scenarios.
Raw rate columns use `summarizeBy: none`; report visuals must use measures rather than sums.

## Calculation group and field parameters

`SemanticModel/specifications/calculation-group.json` defines Actual, Prior Period, Variance,
Variance %, and Scenario behaviour for approved display measures. It intentionally marks YoY as
unsupported because the included evidence is a selected-period snapshot, not a complete point-
in-time series.

`SemanticModel/specifications/field-parameters.json` allowlists governed measures and approved
dimensions. These files are specifications rather than claims that Desktop objects were
successfully created. Apply and test them in Desktop before release.

## Report scaffold and visual contract

PBIR page definitions create empty structural pages for Executive Command Centre, Strategy
Impact, Entity Oversight, Forecast and Stress, Data Quality, and Metric Dictionary. Required
visuals and visible context are specified separately. Empty pages are deliberate: the project
does not fabricate completed visuals that have not been opened and inspected.

Every completed page must visibly show reporting period, comparison period, filter scope,
refresh timestamp, metric-registry version, evidence ID, and the synthetic-data disclaimer.
Portfolio time series, vintages, migrations, detailed root-cause, baskets, vendor capacity
history, and account drill-through require the native application marts and are labelled as
extensions.

The nAIM theme provides a restrained navy, teal, sky, amber, red, and neutral palette. Import it
in Desktop and inspect contrast, small text, conditional formatting, and accessibility before
distribution.

## Desktop reconciliation gate

1. Copy the whole project to a Windows environment with a supported Power BI Desktop.
2. Open `nAIM.pbip` and record the Desktop version.
3. Set `nAIMExportRoot` to the absolute local `Data` directory without committing that value.
4. Refresh all tables and resolve every type or privacy-level error.
5. Confirm five relationships, one-way filters, and unique keys on both one-side tables.
6. Review every measure and format string against the copied metric registry.
7. Apply and test the calculation group and field parameters.
8. Implement the specified visuals and import the theme.
9. Reconcile the selected scope against `Validation/reconciliation_snapshot.csv` within each
   documented tolerance.
10. Complete every item in `Deployment/deployment-checklist.md` and peer-review the PBIP diff.

Static checks cover JSON parsing, report/model pointers, relative-path containment, source and
project hashes, governed metric coverage, TMDL relationship and measure presence, format
strings, prohibited binary files, and likely secrets. Static checks cannot prove that Desktop
will accept or render the project.

## Optional publisher boundary

Publication is disabled by default and performs no authentication or network call. The Python
module exposes a `PowerBIPublisher` protocol so an approved tenant-specific adapter can be
injected. Publication must be explicitly enabled with environment credentials kept outside
source control:

- `NAIM_POWERBI_PUBLISH_ENABLED=true`
- `NAIM_POWERBI_TENANT_ID`
- `NAIM_POWERBI_CLIENT_ID`
- `NAIM_POWERBI_CLIENT_SECRET`
- `NAIM_POWERBI_WORKSPACE_ID`

Enabling publication without complete credentials fails closed. Providing credentials without
an injected approved adapter also fails closed. A real adapter must confirm its target,
preserve the remote operation ID, reconcile the published model, and support rollback. The
capability may move from `INTEGRATION_ONLY` to `LIVE` only after an authorised, successful
publication test is evidenced.
