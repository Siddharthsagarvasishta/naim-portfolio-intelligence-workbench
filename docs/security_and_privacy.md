# Security and Privacy

nAIM contains synthetic demonstration data, but applies controls expected for sensitive portfolio analytics.

## Baseline controls

- Secrets are environment variables or institution-approved secret-store references; none are committed.
- Parameterized queries, typed input validation, bounded file sizes and safe filenames.
- Explicit CORS origins, security headers and rate limits for commentary/export endpoints.
- Role demonstration uses fictional roles: Executive Viewer, Portfolio Analyst, Strategy Analyst, Model Validator and Administrator.
- Authentication is disabled or a documented development stub in the demo; production requires federated identity and authorization.
- Customer/account identifiers are masked in executive views; detailed export access is logged and limited.
- CSV/spreadsheet formula injection is neutralized.
- LLM input excludes raw records and direct identifiers.

## Audit events

Material configuration changes, basket/workspace versions, strategy approvals, alert transitions, investigation actions, commentary generation, detail exports and override decisions record actor, time, old/new values, reason, approval and request/run IDs.

## Threat considerations

Protect against malicious uploads, path traversal, formula injection, prompt injection in free text, unsafe deserialization, excessive queries, unauthorized configuration promotion and evidence tampering. Verify content types; store uploads outside executable paths; scan dependencies; cap rows and request duration.

## Production integration

Adopters must connect enterprise IAM, encryption/key management, audit retention, DLP, vulnerability management, monitoring, incident response and regional data-residency controls. The demo is not a certified security implementation.

