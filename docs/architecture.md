# Architecture

nAIM is the governed analytical layer between institution-neutral source data and enterprise consumption tools. The browser and exports consume the same versioned evidence contract.

## System architecture

```mermaid
flowchart LR
  S["Synthetic / approved source data"] --> V["Validation & quarantine"]
  V --> C["Canonical model"]
  C --> M["Governed metric marts"]
  M --> A["Analytics services"]
  A --> W["Workspaces & baskets"]
  W --> API["Versioned API & evidence contracts"]
  API --> UI["Web workbench"]
  API --> X["Excel"]
  API --> PBI["Power BI"]
  API --> T["Tableau"]
  API --> SAS["SAS"]
  API --> PPT["PowerPoint"]
  A --> AUD["Lineage & audit log"]
  W --> AUD
  API --> AUD
```

## Data flow

```mermaid
flowchart TD
  R["Raw, immutable landing"] --> Q{"Schema / key / business rules"}
  Q -->|Fail critical| Z["Quarantine + failed run"]
  Q -->|Pass| C["Curated conformed entities"]
  C --> F["Monthly facts"]
  F --> G["Metric registry execution"]
  G --> DQ{"Publication gate"}
  DQ -->|Pass or approved warning| E["Versioned evidence snapshot"]
  DQ -->|Fail| Z
  E --> API["API / export adapters"]
```

## Analytical star schema

```mermaid
erDiagram
  DIM_DATE ||--o{ FACT_ACCOUNT_MONTH : dates
  DIM_CUSTOMER ||--o{ FACT_ACCOUNT_MONTH : owns
  DIM_ACCOUNT ||--o{ FACT_ACCOUNT_MONTH : describes
  DIM_PRODUCT ||--o{ FACT_ACCOUNT_MONTH : groups
  DIM_CHANNEL ||--o{ FACT_ACCOUNT_MONTH : acquires
  DIM_GEOGRAPHY ||--o{ FACT_ACCOUNT_MONTH : locates
  DIM_STRATEGY ||--o{ FACT_STRATEGY_DECISION : assigns
  DIM_PARTNER ||--o{ FACT_PARTNER_MONTH : performs
  DIM_VENDOR ||--o{ FACT_VENDOR_MONTH : performs
  DIM_MEMBERSHIP ||--o{ FACT_MEMBERSHIP_MONTH : performs
  DIM_DATE ||--o{ FACT_PARTNER_MONTH : dates
  DIM_DATE ||--o{ FACT_VENDOR_MONTH : dates
  DIM_DATE ||--o{ FACT_MEMBERSHIP_MONTH : dates
```

## Trust boundaries

Source ingestion, calculation, evidence generation and consumption are separate boundaries. Only validated, aggregated evidence reaches executive views. Configuration writes require schema/range/version validation, impact preview and approval. LLM providers receive bounded evidence, never raw customer records.

## Deployment shape

The preferred demo topology is a web client, typed API, analytical service, DuckDB/Parquet analytical store and local configuration registry. Production adoption should replace the development authentication stub, local secrets and single-node storage with institution-approved identity, key management, database, scheduler and observability services.

