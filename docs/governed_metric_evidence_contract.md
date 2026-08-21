# Governed metric evidence contract

The core KPI API is descriptive, source-backed, and fail-closed. The governed metric
registry covers the same 15 metric IDs that the runtime calculation produces; a missing,
extra, or incomplete definition blocks configuration loading.

## API fields

`GET /api/v1/kpis` and the KPI rows within `GET /api/v1/command-centre` expose:

- the primary validated source, exact source fields, source grain, supporting-source joins,
  transformation module/callable/version, and refresh facts;
- a deterministic runtime evidence ID bound to metric value, periods, filters, dataset hash,
  configuration hash, and analytical run ID;
- a configured guardrail rule and evaluated status, including rule version, directionality,
  denominator rule, observed change, applied threshold, and explanation;
- separate sample adequacy, statistical assessment, and practical materiality results;
- metric-specific interpretation boundaries and permitted next action; and
- an explicit cross-artifact reconciliation status.

Ordinary KPI requests report cross-artifact reconciliation as `NOT_RUN`. They never infer
`PASS` from successful calculation or data-quality validation. A conflicting non-null
source-context configuration hash or run ID blocks the response rather than relabelling
foreign provenance. An absent DEMO run ID may fall back to the authoritative deterministic
service run.

`GET /api/v1/metric-registry` returns the same governed definitions plus current runtime
evidence bindings. Root and wheel-bundled copies of `metric_registry.json` must remain
identical.

## Interpretation and status semantics

Sample adequacy answers only whether the configured denominator minimum was met. It uses
`ADEQUATE` or `INADEQUATE`. Statistical assessment is independent and remains `NOT_RUN`
because the ordinary KPI response performs no confidence interval, hypothesis test, or
causal inference. Practical materiality compares the absolute month-over-month change to a
versioned operational threshold; it does not assert statistical significance.

Guardrail statuses are evaluated server-side from registry thresholds in priority order:
`CRITICAL`, `ADVERSE`, `WATCH`, `FAVOURABLE`, then `NEUTRAL`. The directionality and
denominator rule are returned with the result so a client does not recreate threshold
logic.

## Server-observable diagnostics

`GET /api/v1/data-source` keeps active data mode separate from diagnostic state. Its
`diagnostics` object reports server observation time, configured and active modes, snapshot
creation time, maximum data date, age, configured stale threshold, freshness, dataset hash
and hash basis, configuration hash, and run ID. Missing or invalid creation time yields
`UNKNOWN`; it is never promoted to `CURRENT`.

These diagnostics describe only server-observable snapshot facts. They do not claim browser
request history, client fetch recency, or UI cache state. Request correlation remains the
`X-Request-ID` response header and is not analytical evidence.
