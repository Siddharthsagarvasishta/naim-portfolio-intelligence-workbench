# nAIM Capability Status

Registry version: `2.0.0`

This document mirrors `config/feature_status.yaml`, which is authoritative. Run
`python scripts/validate_feature_status.py` to verify schema, evidence paths,
status claims, totals, and table synchronization.

`LIVE` means executable in this repository with focused test evidence. It does
not mean externally hosted, institutionally approved, or production operated.
`INTEGRATION_ONLY` means a real interface, adapter, or interoperability asset
exists, but the end-to-end external capability was not validated. `DOCUMENTED`
means design guidance without an executable implementation. `NOT_IMPLEMENTED`
is an explicit product gap. No capability is currently `DISABLED`.

## Status summary

| Status | Capabilities |
|---|---:|
| `LIVE` | 40 |
| `INTEGRATION_ONLY` | 13 |
| `DOCUMENTED` | 2 |
| `DISABLED` | 0 |
| `NOT_IMPLEMENTED` | 8 |
| **Total** | **63** |

## Capability inventory

| Feature ID | Status | Capability |
|---|---|---|
| `CAPABILITY_STATUS_REGISTRY` | `LIVE` | Capability truth registry |
| `DETERMINISTIC_DATA_PIPELINE` | `LIVE` | Deterministic synthetic data pipeline |
| `DATA_QUALITY_GATE` | `LIVE` | Data validation, quarantine, and publication gate |
| `CORE_PORTFOLIO_ANALYTICS` | `LIVE` | Governed portfolio KPIs and trends |
| `VINTAGE_ROLL_RATE_ANALYTICS` | `LIVE` | Vintage and delinquency-transition analytics |
| `STRATEGY_COMPARISON` | `LIVE` | Champion and challenger strategy comparison |
| `ROOT_CAUSE_DECOMPOSITION` | `LIVE` | Exact mix and within-segment decomposition |
| `ALERT_RULE_EVALUATION` | `LIVE` | Deterministic alert-rule evaluation |
| `POINT_IN_TIME_ANALYTICS` | `LIVE` | Point-in-time bounded analytical views |
| `STATISTICAL_SEGMENTATION` | `LIVE` | K-Means segmentation with a tree surrogate |
| `SCENARIO_FORECASTING` | `LIVE` | Transparent conditional scenario projections |
| `CROSS_DOMAIN_ENTITY_ANALYTICS` | `LIVE` | Partner, vendor, membership, benefit, and rating analytics |
| `FINANCE_NETWORK_CAPACITY_ANALYTICS` | `LIVE` | Financial bridge, dependency-network, and capacity analysis |
| `BASIC_BASKET_WORKSPACE_RUNTIME` | `LIVE` | Durable baskets, workspaces, investigations, and analysis runs |
| `DETERMINISTIC_COMMENTARY_PROVIDER` | `LIVE` | Deterministic evidence-bounded commentary |
| `WEB_WORKBENCH` | `LIVE` | Responsive analytical web workbench |
| `EXCEL_EXPORT_SERVICE` | `LIVE` | API-generated Excel evidence export |
| `API_SAFETY_BASELINE` | `LIVE` | Typed input and bounded output safety controls |
| `PIPELINE_PROVENANCE` | `LIVE` | Pipeline run manifest and configuration provenance |
| `PERFORMANCE_BENCHMARKING` | `LIVE` | Backend response-time benchmark harness |
| `LOCAL_NON_DOCKER_DEPLOYMENT` | `LIVE` | Local API and web startup path |
| `STRICT_DATA_SOURCE_MODES` | `LIVE` | Strict LIVE, DEMO, OFFLINE_SNAPSHOT, and UNAVAILABLE modes |
| `WORKFLOW_STATE_PERSISTENCE` | `LIVE` | Durable mutable workflow state |
| `AUTH_DISABLED_MODE` | `LIVE` | Explicit local-development authentication-disabled mode |
| `AUTH_DEMO_MODE` | `LIVE` | Token-based demonstration authentication |
| `BACKEND_ROLE_ENFORCEMENT` | `LIVE` | Endpoint-level role-based access control |
| `OIDC_AUTHENTICATION` | `INTEGRATION_ONLY` | OIDC authentication adapter |
| `DATA_ONBOARDING_STUDIO` | `LIVE` | Local data onboarding studio |
| `PORTFOLIO_COMPOSITION_OPTIMISER` | `LIVE` | Constrained portfolio composition optimiser |
| `LIVE_PRESENTATION_GENERATION` | `LIVE` | Workspace-driven live presentation generation |
| `MARKET_RISK_VOLATILITY_LAB` | `LIVE` | Market Risk and Volatility Lab |
| `SURVIVAL_ANALYSIS` | `LIVE` | Kaplan-Meier and time-to-event analysis |
| `SHAP_DELINQUENCY_DIAGNOSTICS` | `INTEGRATION_ONLY` | SHAP-supported next-month delinquency diagnostics |
| `CHANGE_POINT_DETECTION` | `LIVE` | Robust structural change-point detection |
| `PROPENSITY_WEIGHTED_COMPARISON` | `LIVE` | Propensity-weighted observational comparison |
| `DIFFERENCE_IN_DIFFERENCES` | `LIVE` | Synthetic-policy difference-in-differences analysis |
| `LEARNING_PROFESSIONAL_MODES` | `NOT_IMPLEMENTED` | Learning and professional analytical modes |
| `GOVERNED_INSIGHT_COMPOSER` | `NOT_IMPLEMENTED` | Structured governed Insight Composer |
| `CUSTOM_METRIC_BUILDER` | `NOT_IMPLEMENTED` | Governed custom metric and analysis builder |
| `REPRODUCIBILITY_PACKS` | `INTEGRATION_ONLY` | User-generated reproducibility packs |
| `EXPORT_JOB_FRAMEWORK` | `INTEGRATION_ONLY` | Persistent asynchronous export-job framework |
| `TABLEAU_STATIC_PACKAGE` | `INTEGRATION_ONLY` | Tableau source and build-guidance package |
| `TABLEAU_HYPER_EXTRACT` | `LIVE` | Validated Tableau Hyper extract |
| `POWER_BI_SOURCE_PACKAGE` | `INTEGRATION_ONLY` | Power BI source-control enablement package |
| `POWER_BI_PUBLISHING` | `INTEGRATION_ONLY` | Authenticated Power BI publication |
| `SAS_INTEROPERABILITY_PACKAGE` | `INTEGRATION_ONLY` | Base SAS interoperability source package |
| `STREAMLIT_COMPANION` | `LIVE` | Restricted Streamlit public companion |
| `STATIC_SHARE_SITE` | `LIVE` | Backend-independent static share site |
| `LINKEDIN_SHOWCASE_PACKAGE` | `INTEGRATION_ONLY` | LinkedIn showcase package |
| `PUBLIC_DEMO_PROFILE` | `INTEGRATION_ONLY` | Restricted public deployment profile |
| `DOCKER_LOCAL_DEPLOYMENT` | `INTEGRATION_ONLY` | Docker local deployment |
| `PRODUCTION_STYLE_DEPLOYMENT` | `DOCUMENTED` | Production-style deployment profile |
| `WORKSPACE_DRIVEN_OUTPUT_BUILDER` | `NOT_IMPLEMENTED` | Workspace-driven multi-format output builder |
| `GOVERNED_DASHBOARD_BUILDER` | `NOT_IMPLEMENTED` | Governed drag-and-drop dashboard builder |
| `CONTROLLED_ANALYSIS_QUERY` | `NOT_IMPLEMENTED` | Controlled natural-language analysis query interface |
| `EXTERNAL_GENAI_PROVIDER` | `DOCUMENTED` | Controlled external generative-AI provider adapters |
| `API_CONTRACT_GENERATION` | `LIVE` | Generated frontend types from the backend schema |
| `ADVANCED_FINANCIAL_SCENARIOS` | `NOT_IMPLEMENTED` | Advanced valuation and probability-weighted financial scenarios |
| `ANALYTICAL_METHOD_COMPARISON_BOARD` | `NOT_IMPLEMENTED` | Analytical Method Comparison Board |
| `FULL_ARTIFACT_PROVENANCE` | `INTEGRATION_ONLY` | Per-artifact manifests and cross-channel provenance |
| `CROSS_ARTIFACT_RECONCILIATION` | `INTEGRATION_ONLY` | Cross-artifact numerical reconciliation |
| `SECURITY_HARDENING` | `LIVE` | Comprehensive application security hardening |
| `THREAT_MODEL` | `LIVE` | Repository threat model and security test report |

## Important boundaries

- SQLite persistence, migrations, optimistic versioning, approvals, and audit
  history are locally validated. PostgreSQL is wired but not exercised against
  managed infrastructure.
- Disabled and demo authentication modes are executable. OIDC remains an
  integration because no real identity provider was available.
- Every data mode is explicit and fail-closed. Analytical point-in-time bounds
  are tested; workflow records are current-state objects with immutable history.
- Hyper generation is native and reopen-tested. Power BI, SAS, Tableau
  publishing, Docker, and public hosting are labelled as integrations because
  their external runtimes or targets were unavailable.
- SHAP itself is not claimed: calibrated behavioural modelling and perturbation
  diagnostics execute, while the optional SHAP dependency remains unavailable.
- Export metadata is durable and downloads are scoped, expiring, authorised,
  hash-verified, and audited; export computation is still synchronous.
- The static share site and Streamlit companion are locally validated public
  surfaces. No external publication or production security posture is implied.
- Advanced observational outputs are labelled associational unless design
  assumptions are independently established.
