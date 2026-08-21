# Report Page Specifications

## Pages supported by the included evidence extracts

| Page | Primary question | Required visuals |
|---|---|---|
| Executive Command Centre | What changed and what needs attention? | KPI strip, selected-versus-prior comparison, quality gate, evidence footer |
| Strategy Impact | What trade-offs are visible, and is causal interpretation blocked? | strategy table, expected-profit bars, fraud/friction comparison, validity warning |
| Entity Oversight | Which partner, vendor or membership entities need review? | rating table, value/cost metrics, entity-type filter |
| Forecast & Stress | What changes under approved assumptions? | scenario profit bars, impact table, scenario notice |
| Data Quality | Is evidence safe to use? | publication status, row count, evidence hash, reconciliation snapshot |
| Metric Dictionary | What does each result mean? | searchable definition, formula, owner, version and caveats |

## Extension pages requiring native application marts

Portfolio time series, vintages, migration/transition analysis, detailed root-cause bridges, baskets, partner concentration, vendor capacity history and account drill-through require the corresponding native marts in `sql/marts/`. They are not represented by the bounded snapshot CSVs and must not be inferred by duplicating or cross-joining the included files.

Use metric field parameters only for governed metric IDs. Tooltips should show prior value, denominator, unit, metric version, evidence ID and source run. Any extension-page drill-through must inherit and display its full filter scope.
