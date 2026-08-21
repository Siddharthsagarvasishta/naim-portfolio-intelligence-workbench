# Tableau Setup

## Package

`exports/tableau/` provides CSV extracts, relationship guidance, calculated fields, parameters, filters, page specifications, accessibility guidance and reconciliation totals. No Hyper file is supplied unless a supported runtime creates and validates it.

## Data model

Prefer Tableau relationships between conformed dimensions and fact tables rather than physical joins that duplicate facts. Define cardinality and referential integrity explicitly. Basket membership uses a bridge at basket-version/member grain.

## Calculated fields

Create rate fields from sums, for example:

`SUM([Net Credit Loss]) / SUM([Average Receivables]) * 12`

Fraud basis points use `SUM([Confirmed Fraud Loss]) / SUM([Transaction Value]) * 10000`. Do not average row-level or pre-aggregated rates. Parameterized comparisons should expose current, prior, YoY, scenario and benchmark while preserving metric version.

## Dashboard guidance

Use a global reporting-period and scope header; one primary analytical question per dashboard; numerator/denominator in tooltips; warning states for small samples, quality and weak peers; drill actions to evidence; and color plus text/icon status cues.

## Refresh and reconciliation

Refresh dimensions before facts, then metric registry and validation snapshot. Verify selected-month totals against `exports/validation/interop_reconciliation_totals.csv`. Record run ID, refresh time and evidence hash in a visible footer. Any material mismatch blocks publishing.
