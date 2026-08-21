# nAIM Tableau Source Package

Load the CSV files in `data/` as logical tables and use relationships rather than fact-duplicating physical joins. The package deliberately contains no fabricated `.hyper` or `.twb`. `evidence_scope.csv` is the shared filter anchor; the KPI, strategy, entity and scenario snapshots remain independent analytical grains.

1. Relate each snapshot to `evidence_scope` on `evidence_scope_key`.
2. Create fields from `calculated_fields.txt`.
3. Create parameters from `parameters.csv`.
4. Apply the visible evidence footer and synthetic-data disclaimer.
5. Reconcile the selected scope to `../validation/interop_reconciliation_totals.csv`.

Use a published data source in a managed deployment. Refresh dimensions/metadata before facts and block report publication if reconciliation exceeds tolerance.
