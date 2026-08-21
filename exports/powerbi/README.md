# nAIM Power BI Evidence Package

This folder is a bounded, build-ready source package for the included flat analytical snapshots; it is not a `.pbix` file and it is not a substitute for the application's full star-schema marts. Use Import mode for the synthetic demo, load every CSV in `data/`, preserve the file-based table names, create only the relationships in `relationships.csv`, paste the snapshot-compatible measures from `measures.dax`, and reconcile the validation page to `../validation/interop_reconciliation_totals.csv`.

The extracts have intentionally separate grains:

| File/table | Grain | Key |
|---|---|---|
| `evidence_scope` | one row per governed evidence run and selected analytical month | `evidence_scope_key` |
| `kpi_snapshot` | metric × evidence scope | `evidence_scope_key`, `metric_id` |
| `strategy_snapshot` | strategy × evidence scope | `evidence_scope_key`, `strategy` |
| `entity_rating_snapshot` | entity × entity type × evidence scope | `evidence_scope_key`, `entity_type`, `entity_id` |
| `scenario_snapshot` | scenario × evidence scope | `evidence_scope_key`, `scenario` |
| `metric_dictionary` | governed metric version | `metric_id`, `metric_version` |

Do not join the four analytical snapshots directly: that would multiply rows across their independent grains. `evidence_scope` supplies the shared filter anchor. For vintage, account-level, transition, decomposition-detail or time-series pages, connect the corresponding native marts documented in `sql/marts/`; those row-level marts are outside this bounded evidence package.

The metric authority remains `../validation/governed_formula_metadata.csv` and `config/metric_registry.json`. Any display measure added to a report must reference the governed numerator/denominator measures rather than redefine the business metric.

Supported and extension pages are documented in `page_specifications.md`. Record the evidence ID, run ID, reporting period, evidence hash and refresh timestamp in a visible report footer.
