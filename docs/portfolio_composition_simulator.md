# Portfolio Composition Simulator

## Purpose

The simulator estimates portfolio outcomes under controlled changes to mix, strategy, partner, vendor, membership or scenario assumptions. It is a decision-support sandbox, not an optimizer that executes changes.

## Inputs

Base workspace and basket versions; proposed weights or swaps; strategy assignment; transition assumptions; capacity and contract constraints; scenario path; metric/configuration version; effective horizon.

## Calculation

Recalculate additive totals and governed ratio-of-sums at the proposed composition. Separate pure mix impact from assumed within-segment performance change. Preserve weight normalization and disclose any residual “unallocated” population.

## Guardrails

- No negative weights; sum within tolerance.
- No entity outside approved eligibility.
- Contract, capacity and concentration limits are explicit.
- Performance assumptions are bounded and versioned.
- Weak or extrapolated cells are warned or suppressed.
- Results are scenario estimates, not guaranteed outcomes.

## Output

Baseline versus proposal, change bridge, risk/profit/customer/operations trade-offs, concentration, capacity, sensitivity range, breached guardrails and required approvals. Saving creates a scenario version with owner, reason and evidence hash.

