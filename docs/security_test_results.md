# nAIM security test results

Executed: 2026-08-01 09:15 UTC; Node dependency audit and regression evidence refreshed 2026-08-08 10:48 UTC  
Environment: macOS 26.5.1 (25F80), arm64, Python 3.12.13, Node 22.17.0, npm 10.9.2  
Overall result: **PARTIAL**

The application-level security controls passed the focused executable suite, and the refreshed Node advisory audit reports zero findings after remediation. The release must not claim a complete security audit because the Python dependency advisory audit, security-specific SAST, Docker/image scanning, and live OIDC/vendor integrations were not validated.

Machine-readable evidence is in `outputs/validation/security_test_results.json` and `outputs/validation/security_scan.json`.

## Executed results

| Check | Result | Executed evidence |
|---|---:|---|
| Focused security/onboarding/auth/persistence/point-in-time suite | PASS | 76 passed, 0 failed, 37 warnings in 6.40 seconds across the 11 focused test files listed below. |
| Authored-surface secret/config scan | PASS WITH WARNINGS | 265 files; 0 errors; 2 warnings. No matched secret value is emitted by the scanner. |
| Python environment consistency | PASS | `pip check` reported “No broken requirements found.” |
| Python dependency advisory audit | NOT RUN | `pip-audit` and Safety are not installed. No package was installed solely to make an audit claim. |
| Node dependency advisory audit | PASS | An authorized registry-backed `npm audit --json` run initially found 21 advisories. Compatible dependency remediation and a clean lockfile reconstruction reduced the refreshed count to zero; lint, typecheck, production build, 13/13 frontend tests, and the live local lifecycle then passed. Evidence: `outputs/validation/npm_audit_before_summary.json` and `outputs/validation/npm_audit_after_summary.json`. |
| Node installed-tree hygiene | WARN | `npm ls --depth=0 --json` now lists two extraneous platform-optional WASM/sharp packages, down from 113 in the prior shared tree. This is a tree-hygiene note, not an advisory finding. |
| Ruff static checks | PASS | `ruff check src tests scripts` returned “All checks passed.” |
| Security-specific SAST | NOT RUN | Bandit and Semgrep are not installed. Ruff is lint/static checking, not a substitute for SAST. |
| Docker/image scan | NOT RUN | Docker is unavailable in this environment. |

## Directive control matrix

| Required control | Result | What was exercised | Evidence |
|---|---:|---|---|
| Dependency audit | PARTIAL | Local Python consistency passed and the Node advisory audit passed with zero findings after remediation; Python vulnerability advisory tooling was not available. | This report; `pyproject.toml`; `requirements.lock`; `package-lock.json`; `outputs/validation/npm_audit_after_summary.json` |
| Secret scan | PASS WITH WARNINGS | High-confidence provider tokens, private keys, password-bearing URIs, sensitive literal assignments, client-public secret names, wildcard CORS, and unsafe local deployment defaults. Values are redacted and one-way fingerprinted. | `scripts/security_scan.py`; `tests/unit/test_security_release_audit.py`; `outputs/validation/security_scan.json` |
| Static analysis | PARTIAL | Ruff passed all Python source, tests, and scripts. No security-specific SAST engine ran. | Ruff execution recorded above |
| SQL-injection tests | PASS | PostgreSQL descriptor/table input rejects semicolon, quote/union, excess qualification, and traversal payloads. Database table paths are identifier-validated; arbitrary query text is not accepted. | `tests/unit/test_security_release_audit.py`; `src/naim_risk/onboarding.py` |
| Path-traversal tests | PASS | Upload/select traversal, absolute paths, unregistered hashes, and symlink sources rejected; export paths are contained to the governed directory. | `tests/unit/test_onboarding.py`; `tests/integration/test_onboarding_api.py`; `tests/integration/test_service_workflow_persistence.py` |
| File-upload validation | PASS | Byte/row/column bounds, suffix allowlist, immediate parse, malformed/suffix-spoofed data, external XLSX links, formulas, embedded objects, macros, unsafe members, database access modes, and source SHA-256. | `tests/unit/test_onboarding.py`; `tests/integration/test_onboarding_api.py` |
| Decompression-bomb protection | PASS | XLSX expanded-member metadata above the bound is rejected before workbook parsing. | `tests/unit/test_security_release_audit.py` |
| CSV formula-injection protection | PASS | Export strings beginning `=`, `+`, `-`, or `@` are apostrophe-neutralized; uploaded XLSX formulas are rejected. | `tests/unit/test_security_release_audit.py`; `tests/unit/test_onboarding.py` |
| Rate limiting | PASS | Bounded sliding-window capacity and API 429 response with retry/remaining metadata. | `tests/unit/test_security_controls.py`; `tests/integration/test_security_api.py` |
| Security headers | PASS | Restricted CSP, frame denial, MIME sniffing denial, referrer/permissions/cache headers, request ID, and data-mode header. Interactive API docs retain their explicitly allowlisted CDN dependency. | `tests/integration/test_auth_data_mode_api.py`; `tests/integration/test_security_api.py` |
| CORS validation | PASS | Configured local origin accepted; an untrusted origin receives no allow-origin header and a failed preflight. Credentials are disabled. | `tests/integration/test_security_release_api.py` |
| Token expiration | PASS | Demo JWT expiry validation and HMAC download tokens bound to exact user/resource with a bounded TTL; tampering and expiry rejected. | `tests/unit/test_auth.py`; `tests/unit/test_security_controls.py` |
| Authorization tests | PASS | Missing identity, viewer restrictions, analyst permissions, logout revocation, and backend permission checks. | `tests/unit/test_auth.py`; `tests/integration/test_auth_data_mode_api.py` |
| Download authorization | PASS | Authentication occurs before artifact resolution; HMAC link is subject/resource-scoped; missing/invalid token is rejected; successful downloads persist actor/count/time. | `tests/integration/test_security_release_api.py`; `tests/integration/test_security_api.py`; `tests/integration/test_pipeline_api.py` |
| Audit-log integrity | PASS | Hash chain validates normal history and fails after direct database payload mutation. | `tests/integration/test_workflow_persistence.py`; `tests/unit/test_security_release_audit.py` |
| Tampered-artifact integrity | PASS | Registered export replacement is detected by size/SHA-256 revalidation, records `integrity_failed`, and fails closed. | `tests/integration/test_service_workflow_persistence.py`; `src/naim_risk/service.py` |
| Safe temporary-file cleanup | PASS | Failed onboarding upload removes its generated staging directory; successful Power BI package generation removes its context-managed staging directory. | `tests/unit/test_security_release_audit.py`; `tests/integration/test_security_release_api.py` |

## Focused test files

- `tests/unit/test_security_controls.py`
- `tests/unit/test_security_release_audit.py`
- `tests/unit/test_onboarding.py`
- `tests/unit/test_auth.py`
- `tests/integration/test_security_api.py`
- `tests/integration/test_security_release_api.py`
- `tests/integration/test_auth_data_mode_api.py`
- `tests/integration/test_onboarding_api.py`
- `tests/integration/test_workflow_persistence.py`
- `tests/integration/test_service_workflow_persistence.py`
- `tests/integration/test_pipeline_api.py`

## Secret/config scan interpretation

The scanner reported no error-severity finding. It intentionally reported these two warnings in `docker-compose.yml`:

1. `NAIM_AUTH_MODE` defaults to `disabled` for local setup.
2. `NAIM_TOKEN_SECRET` permits an empty default; authenticated modes validate their required secret and fail closed.

Those defaults are acceptable only on a private local machine. A deployment must set OIDC or governed demo authentication and a managed secret. The scan covers authored text surfaces only. It excludes local `.env`, generated data/artifacts, dependency directories, binaries, Git history, caches, and frozen migration evidence; therefore it cannot prove the absence of secrets.

## Known residual risk

- Real OIDC issuer, JWKS, claim mapping, revocation, and role behavior were not tested against an identity provider.
- Disabled-auth mode is administrator-equivalent and must never be exposed to an untrusted network.
- All defined roles currently include artifact-download permission; production entitlements should be narrower.
- The rate limiter is process-local, so multi-node enforcement and denial-of-service protection require ingress infrastructure.
- Artifact size/hash is verified before response streaming. Protected/versioned object storage is still required to close the privileged local time-of-check/time-of-use window.
- The audit chain is not signed or externally anchored; a database administrator can rewrite both data and hashes.
- Upload parsing is bounded but has no antivirus, content-disarm, file reputation, or isolated parser service.
- No Python dependency vulnerability-advisory status, security-specific SAST status, container status, or production penetration-test status is available from this run.
- The rebuilt Node tree has two extraneous platform-optional WASM/sharp entries. They are not advisory findings, but a final distribution environment should still reconstruct from `package-lock.json` and rerun the advisory and regression checks.

## Commands executed

```text
PYTHONPATH=src .venv/bin/python -m pytest <11 focused test files>
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python -m pip check
.venv/bin/python scripts/security_scan.py --compact
npm ls --depth=0 --json
npm audit --json
```

The original Node audit attempt was blocked. The 2026-08-08 refresh used an authorized registry-backed audit, performed compatible dependency remediation, reconstructed from the lockfile, and passed the post-remediation frontend and live-lifecycle regression checks.
