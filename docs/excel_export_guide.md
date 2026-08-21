# Excel Export Guide

## Workbook contract

The workbook is a governed point-in-time snapshot for review and controlled configuration exchange. It is not a second metric engine. Formula-driven presentation tabs reference visible source/control tables; governed definitions remain tied to metric IDs and versions.

Recommended tabs are Executive Summary, KPI Trends, Portfolio Segments, Vintage Analysis, Strategy Comparison, Root-Cause Analysis, Alerts, Investigation Queue, Scenario Forecast, Data Quality, Metric Dictionary, Assumption Control, Metric Thresholds, Alert Rules, Rating Weights, Basket Definitions, Basket Membership, Scenario Assumptions, Presentation Mapping, Export Settings and Refresh Control.

## Editing controls

Editable inputs are visually distinct, typed and bounded. An uploaded control workbook must pass:

1. workbook and table schema validation;
2. numeric and enum range checks;
3. current-version match;
4. authorized-owner and approval status;
5. change summary and impact preview;
6. audit-log creation.

Uploading never overwrites an approved configuration silently.

## Refresh

Record source run ID, evidence hash, reporting period, generated time, metric registry version and filter scope on Refresh Control. A refresh imports versioned extracts into named tables, recalculates formulas and reruns the reconciliation block before distribution.

## Reconciliation

Check active accounts and additive monetary totals, then numerator/denominator/rate triples. Basis-point movements use unrounded source values. Root-cause mix plus performance must equal the observed change within tolerance. The workbook's evidence tables reconcile to `exports/validation/interop_reconciliation_totals.csv`.

## Security

Keep macros disabled unless the optional source modules have been reviewed, signed and distributed under enterprise policy. Formula-like text is escaped. Avoid embedding credentials or user-specific paths. Use the non-macro CSV/Power Query route where practical.
