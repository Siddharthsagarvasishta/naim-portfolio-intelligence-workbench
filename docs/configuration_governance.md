# Configuration Governance

## Governed objects

Metric definitions, thresholds, alerts, ratings, baskets, workspaces, scenarios, contracts, presentation mappings, exports, models, peer rules and onboarding mappings.

## State model

Draft → validated → impact reviewed → approved → effective → superseded/retired. Rejected versions remain auditable. Only approved effective versions can drive published evidence.

## Change controls

Every change stores old/new values, owner, reason, effective date, validation results, affected metrics/workspaces/dashboards/reports/ratings/alerts/historical periods, approver and timestamps. Material changes require independent review.

## Separation of duties

Authors cannot self-approve high-materiality methodology changes. Administrators manage access but do not become analytical approvers by default. Emergency overrides have expiry and retrospective review.

## Excel/API imports

Imports pass schema, type, range, enum, referential-integrity and current-version checks. The system displays a normalized diff and analytical impact preview before saving a draft. No import directly overwrites production configuration.

## Reproducibility

Published evidence records the exact configuration hash and object versions. Historical output can be rerun against frozen configuration or intentionally restated with a new version and reconciliation.

