# Basket and Workspace Guide

## Basket types

Baskets can contain customer, account, product, membership, partner, vendor, geography, strategy, vintage, benefit or cross-domain members. A definition can be dynamic (re-evaluated on refresh) or frozen (exact membership retained).

## Set and weighting operations

`UNION`, `INTERSECT` and `EXCEPT` create a new version with parent lineage. Reweighting declares equal, account, balance, transaction, expected-profit, contractual-exposure, benefit-cost, process-volume or user-defined weights. Displays distinguish totals, weighted averages, simple averages, medians and percentiles.

## Version workflow

1. Draft a definition and effective date.
2. Validate permitted fields, operators and grain.
3. Preview member count, changed members, weight sum and metric impact.
4. Record reason and owner.
5. Approve/lock or reject.
6. Run analyses against the immutable version ID.

Clone, archive, share, compare, merge, intersect, subtract, exclude, component swap and point-in-time snapshot actions all create audit events.

## Workspace

A workspace stores the business question, basket versions, reporting/comparison periods, metrics, dimensions, filters, analytical templates, scenario, commentary settings, notes and export mapping. Refreshing a workspace uses a new data run while preserving the approved configuration, then highlights evidence changes from the prior approved run.

## Templates

Monthly Portfolio Review, Weekly Emerging-Risk Review, Partner Performance Review, Vendor Oversight Review, Membership Profitability Review, Strategy Test Review, Vintage Deterioration Investigation, Fraud Operations Review, Forecast and Stress Review and Executive Business Review.

## Reproducibility

Every saved result binds `workspace_version + basket_version + metric_registry_version + configuration_hash + data_run_id`. Without this tuple, a screenshot or export is not treated as reproducible evidence.

