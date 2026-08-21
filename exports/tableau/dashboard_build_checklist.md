# Tableau Workbook Build Checklist

- [ ] Evidence ID, run ID, reporting period, metric version and synthetic disclaimer visible.
- [ ] Logical relationships used; no duplicated fact totals.
- [ ] Rates calculated as ratio-of-sums.
- [ ] Small samples and data-quality failures suppressed or warned.
- [ ] Root-cause bridge reconciles before display rounding.
- [ ] Filters map to approved canonical dimensions.
- [ ] Tooltips show numerator, denominator, sample and source run.
- [ ] Dashboard actions preserve scope and expose evidence.
- [ ] Status uses text/icon in addition to color.
- [ ] Sequential palettes for magnitude; diverging palettes only around a meaningful zero.
- [ ] Contrast and keyboard navigation checked.
- [ ] Selected-snapshot totals match `interop_reconciliation_totals.csv`.
- [ ] Extract refresh records source time and evidence hash.

Recommended dashboard silhouettes: executive command centre; portfolio trend; maturity-aligned vintage; strategy trade-off; partner/vendor control towers; root-cause bridge; forecast/stress; quality/lineage.

