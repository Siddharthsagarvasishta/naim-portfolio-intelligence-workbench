# Governed Metric Dictionary

The machine-readable authority is `config/metric_registry.json`. This guide explains the operating rules; exports must use the registry IDs and versions rather than reimplementing formulas.

| Metric ID | Definition | Aggregation | Key safeguard |
|---|---|---|---|
| `ACTIVE_ACCOUNTS` | distinct eligible open, non-charged-off accounts | non-additive over time | period-end eligibility |
| `ACCOUNT_GROWTH` | ending active / beginning active − 1 | non-additive | expose openings and attrition |
| `ENDING_RECEIVABLES` | sum ending balance | semi-additive over time | report currency |
| `UTILIZATION` | sum balance / sum credit limit | ratio of sums | exclude zero limits |
| `DELINQUENCY_30_ACCOUNT_RATE` | 30+ accounts / eligible active accounts | ratio of sums | no average of segment rates |
| `ANNUALISED_NET_LOSS_RATE` | (charge-offs − recoveries) / average receivables × 12 | non-additive | annualisation is not a forecast |
| `FRAUD_BPS` | confirmed fraud loss / transaction value × 10,000 | ratio of sums | zero-denominator guard |
| `MANUAL_REVIEW_RATE` | manual reviews / eligible decisions | ratio of sums | align decision population |
| `FALSE_POSITIVE_RATE` | legitimate flagged / resolved flags | ratio of sums | unresolved flags excluded |
| `CUSTOMER_FRICTION_RATE` | customers with qualifying friction / active transacting customers | non-additive | confirmed fraud is not avoidable friction |
| `ATTRITION_RATE` | attritions / beginning active accounts | non-additive | charge-off closures separate |
| `EXPECTED_PROFIT` | revenue − funding − operating − credit − fraud − review − friction cost | additive | expose every assumption |

## Change and reconciliation

Period changes use full-precision values; basis-point change is `(current_rate - prior_rate) × 10,000`. A segmented rate is always recomputed as the ratio of summed numerators and denominators. Mix/performance attribution must reconcile to the exact portfolio rate change within the configured rounding tolerance.

## Metric contract

Every metric response includes: metric ID, display name, formula description, numerator, denominator, exclusions, unit, aggregation behaviour, minimum sample rule, owner, version, effective date, data-quality status and source lineage.

## Extended metrics

Partner contribution, vendor unit cost, SLA breach rate, benefit utilization, membership contribution, concentration, rating score, rating migration, scenario impact and weighted basket metrics follow the same contract. Weighting is declared as account, balance, transaction, exposure, profit, volume or user-defined; a weighted result must never be labelled a portfolio total.

