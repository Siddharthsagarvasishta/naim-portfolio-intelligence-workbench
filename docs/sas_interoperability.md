# SAS Interoperability

`exports/sas/` is Base SAS-compatible source for import, metric reconciliation, summary, strategy, survival and ODS Excel examples. It is a compatibility package, not the core calculation engine.

## Use

1. Edit the root path macro in the approved local setup.
2. Run `01_import_data.sas` to load typed CSV evidence and dictionaries.
3. Run `02_validate_metrics.sas`; confirm expected totals and tolerance results.
4. Use the analytical examples only after reconciliation passes.
5. Export approved results with `06_export_results.sas`.

Dates are ISO strings imported with `yymmdd10.` and formatted with `yymmdd10.`. Currency and rates remain numeric. Identifiers remain character.

## Governed logic

Scripts import formula metadata and compare outputs with the evidence snapshot. They must not independently redefine a metric. PROC SQL examples calculate numerator/denominator ratios solely for reconciliation.

## Expected outputs

Validation tables, portfolio summaries, strategy frequency/mean tables, illustrative logistic/survival results where sufficient data exists, and an ODS Excel workbook. Output content depends on a SAS runtime and source extract; this repository does not claim these scripts were executed.

## Controls

Review local paths, permissions, log warnings, truncation, missing values, sort order and row counts. Treat any automatic character-to-numeric conversion or uninitialized variable note as a failed run until explained.

