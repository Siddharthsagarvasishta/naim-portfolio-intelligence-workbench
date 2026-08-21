# Data Dictionary

## Conventions

- Dates use ISO `YYYY-MM-DD`; monthly grains use period-end dates.
- Monetary fields are decimal currency units with a separate currency attribute where contracts require it.
- Rates are stored as decimals; basis-point metrics are calculated at consumption.
- Identifiers are text, synthetic and non-semantic.
- Every analytical row carries `run_id`, `source_version`, `data_quality_status` and `synthetic_data_flag`.
- Missing means unknown; zero means a measured absence. They are never interchangeable.

## Core entities

| Entity | Grain | Primary key | Purpose |
|---|---|---|---|
| `customer_account_master` | account | `account_id` | Origination, product, channel, geography and customer linkage |
| `monthly_account_performance` | account-month | `account_id, month` | Balance, payment, delinquency, loss, transaction and friction outcomes |
| `risk_strategy_history` | strategy-version interval | `strategy_id, version, effective_start_date` | Effective-dated rules and approvals |
| `strategy_decision_fact` | decision | `decision_id` | Assignment, treatment and outcome evidence |
| `economic_scenario_assumptions` | scenario-variable-period | composite | Versioned macro and operating assumptions |
| `alert_configuration` | alert-rule version | `alert_rule_id, version` | Threshold, persistence, suppression and ownership |
| `investigation_log` | investigation event | `investigation_id, event_timestamp` | State, owner, evidence and decision history |

## Extended entities

| Entity | Grain | Key measures |
|---|---|---|
| `partner_master` / `partner_contract` | partner / contract version | type, criticality, regions, revenue share, SLA, approval |
| `partner_monthly_performance` | partner-product-region-tier-month | acquisition, spend, loss, cost, complaints, SLA, expected profit |
| `vendor_master` / `vendor_contract` | vendor / contract version | service, criticality, cost, capacity, security and operational ratings |
| `vendor_monthly_performance` | vendor-service-region-product-month | volume, cycle time, quality, errors, incidents, cost and capacity |
| `membership_master` | membership tier | proposition, fee, benefits and effective dates |
| `membership_monthly_performance` | tier-product-region-month | engagement, benefit use, retention, losses and contribution |
| `basket_definition` | basket version | expression, weighting, dynamic/frozen status, owner and approval |
| `basket_membership` | basket version-member | member, effective dates, weight and inclusion reason |
| `workspace_definition` | workspace version | question, periods, metrics, dimensions, methods and exports |

## Data type and rule examples

| Field | Type | Rule |
|---|---|---|
| `account_balance` | decimal(18,2) | may be negative only for documented credit balances |
| `credit_limit` | decimal(18,2) | non-negative; zero-limit rows excluded from utilization denominator |
| `days_past_due` | integer | 0–999; bucket mapping is configuration-controlled |
| `confirmed_fraud_loss` | decimal(18,2) | non-negative; confirmed outcomes only |
| `strategy_assignment` | text | must resolve to an effective approved strategy version |
| `capacity_utilisation` | decimal | non-negative; values above 1 are permitted and signal overload |
| `data_quality_status` | enum | `PASS`, `WARNING`, `FAIL`, `QUARANTINED` |

## Slowly changing dimensions

Product, partner, vendor, membership, strategy and rating methodologies use effective dating. Facts join to the version active on the event date. Backfills never silently overwrite approved history; they create a new run and a reconciliation delta.

