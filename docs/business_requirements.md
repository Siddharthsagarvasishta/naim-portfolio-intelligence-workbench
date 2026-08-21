# nAIM Business Requirements

## Purpose

nAIM is an institution-neutral portfolio risk and profitability workbench. It turns validated synthetic portfolio data into governed metrics, reproducible diagnostics, controlled scenarios, investigations and export packages. It complements—not replaces—enterprise BI, statistical and workflow platforms.

## Decisions supported

1. What changed and is the movement material?
2. Which customer, account, product, channel, vintage, partner, vendor, membership or strategy populations explain it?
3. Is the signal deterioration, mix shift, model drift, operational constraint or data-quality failure?
4. What targeted investigation or controlled strategy response should management consider?

## Required capabilities

- Canonical monthly facts at declared grains, deterministic synthetic data and lineage.
- Versioned metric, alert, rating, scenario and basket definitions.
- Portfolio trends, maturity-aligned vintages, exact mix/performance decomposition, strategy guardrails, drift, forecasting and stress.
- Partner, vendor, customer and membership economics in one governed model.
- Dynamic and frozen baskets; reusable, versioned analytical workspaces.
- Evidence-backed alerts and human-owned investigations.
- Draft-only GenAI commentary constrained to a numerical evidence contract.
- Reconciled Excel, Power BI, Tableau, SAS and editable PowerPoint outputs.

## Non-functional requirements

- Publication gates for critical data-quality failures.
- No unsupported numerical claims; all material results carry metric/configuration versions.
- Non-causal language for observational comparisons and SHAP explanations.
- Synthetic identifiers masked in executive views.
- Accessible, responsive user interface with explicit loading, empty and error states.
- Reproducible runs, deterministic seeds, audit events and safe export filenames.

## Acceptance criteria

The command centre must reconcile to the governed metric layer; the loss-rate bridge must sum to the observed change; maturity-aligned vintage results must expose sample sizes and intervals; strategy output must show validity and operational guardrails; exports must reconcile to a selected snapshot; critical quality failures must block publication; and AI text must be marked as draft and rejected when it contains unsupported numbers.

