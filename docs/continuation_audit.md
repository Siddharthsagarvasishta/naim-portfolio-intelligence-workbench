# nAIM continuation audit

Audit date: 1 August 2026  
Target product: **nAIM Portfolio Intelligence Workbench**  
Pronunciation: “name”  
AIM: **All Is Mine**  
Tagline: **Name the movement. Own the evidence.**

## Executive finding

The supplied application has a reproducible analytical core and a substantial working web/API baseline, but it is not yet a hardened nAIM release. The continuation rerun confirms 46 passing Python tests at 90.09% coverage, a passing deterministic 25,000-account pipeline with a 100/100 quality gate, a passing frontend production build, and four passing rendered-route tests. Existing Excel and PowerPoint packages are structurally valid.

Release blockers are material and explicit:

- Eight API operations return HTTP 501: four onboarding operations, composition scenario execution, optimisation, presentation generation, and presentation status.
- Mutable investigations, baskets, workspaces, analysis runs, export jobs, and demo runs are process-local dictionaries and disappear after restart.
- Authentication, backend role enforcement, signed sessions, OIDC integration, and governed download authorization are absent.
- The frontend starts with seeded data and merges partial live API responses into it, creating a disclosed “hybrid” state that can make seeded facts appear live.
- Point-in-time controls protect many core analytical paths but do not cover all modules, configuration versions, templates, and exports; there is no future-row invariance suite.
- Several visible workflows are illustrative, inert, or locally mocked despite nearby live APIs.
- All existing release artifacts retain the retired public brand; no required nAIM release package exists.
- Existing social evidence conflicts materially with governed calculations and must not be reused.

The baseline is therefore suitable for controlled continuation, not for an unqualified completion or deployment claim.

## Audit method and preservation

Three independent read-only audits covered source/API/UI, quantitative/security/persistence, and artifacts/public readiness. The main verification then reran the original test suite, static checks, production build, model-registry validation, deterministic data pipeline, governed demo calculation, and warm benchmark.

The supplied folder is not a Git repository. No migration tag can be created. Pre-migration control-file and artifact hashes are preserved in `outputs/migration/before_migration_manifest.json`; current rerun evidence is in `outputs/migration/baseline_verification_2026-08-01.json`.

The local `.env` was not inspected or exposed. The unrelated virtual environment and Node installation accidentally created in the user's home folder were not changed.

## Status taxonomy

| Status | Meaning |
|---|---|
| VERIFIED_WORKING | Executable implementation with current passing evidence. |
| WORKING_BUT_INCOMPLETE | Real implementation exists, but a required boundary or workflow is missing. |
| MOCKED_OR_ILLUSTRATIVE | Visible behavior is seeded, hard-coded, local-only, inert, or not connected to the governed service. |
| UNTESTED | Implementation exists, but the relevant boundary lacks current evidence. |
| INTEGRATION_ONLY | Source material or a deliberate unavailable response exists; no supported live execution exists. |
| DOCUMENTATION_ONLY | Method or integration is described but not executable in the product. |
| NOT_IMPLEMENTED | Required capability is absent. |

## Independently verified baseline

| Area | Result | Current evidence |
|---|---:|---|
| Python/API tests | PASS | 46 passed, 0 failed, 51 warnings |
| Python/API coverage | PASS | 2,563 of 2,845 statements; 90.0879% |
| Ruff check | PASS | No findings |
| Ruff format check | PASS | 73 files already formatted |
| Frontend type check | PASS | Passed after lockfile-defined project dependency reinstall |
| Frontend lint | PASS | Passed |
| Production frontend build | PASS | vinext build completed |
| Rendered-route tests | PASS | 4 passed, 0 failed |
| Model registry | PASS | 4 models, 3 feature groups, 0 failures |
| Default pipeline | PASS | 43.29475 seconds; publication allowed |
| Data quality | PASS | 100/100; no rejected rows |
| Data volume | PASS | 25,000 accounts; 513,923 account-months; 513,573 strategy decisions |
| Storage | PASS | DuckDB and 62 Parquet files; 204,644 KiB under `data/` |
| Governed demo | PASS | Live calculations and commentary verification PASS |
| Docker execution | UNTESTED | Docker unavailable on the observed machine |
| Hosted deployment | NOT_IMPLEMENTED | No Sites project ID or storage bindings |

The first continuation type check failed because the supplied `node_modules` contained hundreds of duplicate directories suffixed with ` 2`. A project-local `npm ci` rebuilt dependencies from `package-lock.json`; type check, lint, build, and rendered tests then passed. A deliberately parallel pair of builds also collided in the shared output directory; the supported sequential run passed. Neither failure is attributed to product source behavior.

## Frontend inventory

Eighteen intended views are declared: Executive, Trends, Root Cause, Vintage, Strategy, Partners, Vendors, Membership, Baskets, Finance, Data Quality, Forecast, Alerts, Investigations, Model Monitoring, Methodology, Exports, and Instant Demo. The route dispatcher renders all intended keys.

| Finding | Status | Evidence |
|---|---|---|
| Intended view dispatcher | VERIFIED_WORKING | `app/workbench-types.ts`, `app/components/pages.tsx` |
| Root and named dynamic views | WORKING_BUT_INCOMPLETE | `app/page.tsx`, `app/[view]/page.tsx` |
| Unknown route handling | DEFECT | Unknown one-segment slugs silently render Executive with HTTP 200 instead of a not-found response. |
| Route tests | WORKING_BUT_INCOMPLETE | Only Executive and six named routes are sampled; all 18 are not exercised. |
| Brand regression | NOT_IMPLEMENTED | Existing tests explicitly assert the retired brand. |

### Live/demo boundary defect

`app/data/api-client.ts` constructs seeded data first, fetches only a subset of APIs, spreads live fragments over seeded structures, and keeps seeded fallbacks for missing fields and failed optional calls. `app/workbench.tsx` labels the result “Hybrid source.” The type model supports only API or synthetic-demo, not LIVE, DEMO, OFFLINE_SNAPSHOT, UNAVAILABLE.

Examples of seeded values surviving a nominally live view include roll rates, commentary, data-quality lineage, scenario metadata, membership transitions, and fallbacks inside Finance and Root Cause. This violates the required non-blending rule. The current state is **WORKING_BUT_UNSAFE** and is a release blocker.

### Mocked or incomplete visible workflows

- Entity scenarios use browser-local illustrative arithmetic rather than the existing backend scenario services.
- Membership transition matrices are hard-coded despite a backend endpoint.
- Basket overlap ratios are hard-coded; creation is disabled in API mode and workspace template buttons are inert.
- Generic download controls only display “Export queued” and do not download a file.
- Instant Demo contains hard-coded champion/challenger and scenario fallbacks, a fake investigation record, a local commentary step, and claimed export queuing without export API calls.
- Methodology export cards are inert despite reconciliation language.

These surfaces are **MOCKED_OR_ILLUSTRATIVE** or **WORKING_BUT_INCOMPLETE**, not live evidence.

## API inventory

The FastAPI application has 80 decorated operations: 47 GET, 30 POST, and 3 PATCH.

### Explicit HTTP 501 operations

| Operation | Baseline status |
|---|---|
| `POST /api/v1/data-onboarding/preview` | INTEGRATION_ONLY |
| `POST /api/v1/data-onboarding/map` | INTEGRATION_ONLY |
| `POST /api/v1/data-onboarding/validate` | INTEGRATION_ONLY |
| `POST /api/v1/data-onboarding/load` | INTEGRATION_ONLY |
| `POST /api/v1/composition-scenarios/run` | INTEGRATION_ONLY |
| `POST /api/v1/optimisation/run` | INTEGRATION_ONLY |
| `POST /api/v1/presentations/generate` | INTEGRATION_ONLY |
| `GET /api/v1/presentations/{presentation_id}` | INTEGRATION_ONLY |

The first six have direct integration-test evidence for the 501 contract; the two presentation placeholders do not. `GET /api/v1/presentations` returns HTTP 200 but explicitly reports the integration as unavailable.

Thirty of the 80 operations have no direct route-string test reference, including health and metadata, KPI/vintage/roll-rate/segment/drift variants, several partner/vendor/membership aliases, basket combination and impact operations, ratings calculations, network/capacity scenarios, demo status, and all presentation routes. Some have service-level coverage, so they are **UNTESTED_AT_HTTP_BOUNDARY**, not automatically broken.

## Data pipeline, quality, and ground truth

The deterministic data generator, raw/validated/curated layers, DuckDB views, Parquet marts, quarantine flow, validation gate, manifests, and matching-run reload are **VERIFIED_WORKING**.

The pipeline removes test ground truth from analytical frames and persists it only below `data/demo/ground_truth`; the release pack excludes that directory. Normal analytics and UI do not consume its contents. However, the API-sanitized manifest still reveals a `test_only.ground_truth` key and basename, while the persisted manifest contains a full absolute path. The API should remove the test-only member entirely.

Generated manifests also contain user-specific absolute paths. Current runtime responses sanitize selected paths to basenames, but public provenance must use portable relative identifiers.

## Point-in-time controls

Core reporting-period bounds are real and covered across command-centre metrics, trends, alerts, root cause, vintages, roll rates, strategy comparisons, scenarios, commentary, partner/vendor/membership analytics, benefits, and Finance. Membership effective dates are applied.

Coverage is incomplete:

- Segmentation and drift use full-history data and expose no reporting period.
- Peer analogues, network, and capacity use unbounded data.
- Rating/configuration and scenario-assumption versions are not effective-dated.
- Basket impact selects a latest global partner month.
- Workspace, basket, and investigation state is current-state only.
- Some entity performance paths bound facts but pass unversioned full contract tables.
- Template execution ignores requested periods for several templates.
- Demo execution selects a peak period but calls an unbounded strategy comparison.
- No test appends future rows and proves every historical API/export value remains invariant.

Classification: core **VERIFIED_WORKING**; cross-domain, configuration, template, workflow, and export invariance **WORKING_BUT_INCOMPLETE/UNTESTED**.

## Workflow persistence

Analytical datasets persist. Mutable workflow state does not.

`WorkbenchService` initializes investigations, baskets, workspace overrides, analysis runs, export artifacts, and demo runs as process-local dictionaries. Their CRUD paths work in one process, but data disappears on restart. There is no SQLAlchemy model, Alembic migration, PostgreSQL adapter, optimistic-concurrency check, soft deletion, immutable history, or restart-persistence test. The frontend Drizzle schema is empty and D1/R2 bindings are null.

Classification: analytical persistence **VERIFIED_WORKING**; mutable workflow persistence **NOT_IMPLEMENTED**.

Some prior checklist language describes saved workspaces and an audit trail too strongly and must be corrected until restart and history evidence exists.

## Authentication and authorization

There is no configurable authentication mode, login/token/logout flow, modern password hashing, signed expiring session token, OIDC adapter, FastAPI security dependency, user/role model, endpoint authorization, or download authorization. All mutation and download routes are anonymous.

`app/chatgpt-auth.ts` is an unused upstream-header helper, not a governed authentication system. The UI hard-codes “Portfolio Analyst / Demo role.”

Classification: **NOT_IMPLEMENTED**.

## Security baseline

### Implemented controls

- Strict Pydantic request models with forbidden extra fields and bounds.
- Explicit CORS origins with credentials disabled.
- Request IDs and structured request logs.
- Manifest path-containment checks.
- Safe artifact identifiers without raw download paths.
- Quarantine path basename sanitization.
- An AST allowlist for basket expressions that rejects calls and arbitrary code.
- Spreadsheet formula-prefix neutralization for `=`, `+`, `-`, and `@`.

### Missing or overstated controls

- Authentication, authorization, role checks, expiry, and logout.
- Security headers and content-security policy.
- Rate limiting and abuse controls.
- Upload type/size/bomb validation.
- Dependency audit, secret scan, and SAST in CI.
- SQL injection, traversal, unauthorized-download, cleanup, and tamper-evidence tests.
- Durable audit records.
- Formula neutralization for leading tab and carriage-return characters.

`docs/security_and_privacy.md` currently overclaims bounded uploads, security headers, rate limits, role-limited/logged downloads, and persisted audit events. Those claims must be removed or backed by implementation.

## Quantitative capability audit

| Capability | Baseline status | Finding |
|---|---|---|
| Core portfolio metrics/root cause | VERIFIED_WORKING | Reconciled deterministic evidence and passing tests. |
| Market Risk and Volatility Lab | NOT_IMPLEMENTED | No market-data protocol, route, module, models, exports, or tests. |
| Survival analysis | DOCUMENTATION_ONLY | Registry/SAS templates only; no live model or supported row-level input. |
| SHAP | DOCUMENTATION_ONLY | Registry label and UI disclosure; no trained explainable model or SHAP dependency. |
| Change-point detection | DOCUMENTATION_ONLY | Catalogue mention only. |
| Propensity-weighted comparison | DOCUMENTATION_ONLY | No propensity model, balance checks, weights, or estimates. |
| Difference-in-differences | DOCUMENTATION_ONLY | Registry label only; live execution rejects it. |
| Data Onboarding Studio | INTEGRATION_ONLY | Four 501 routes and a guide; no parser, profile store, approval, or connectors. |
| Composition optimiser | INTEGRATION_ONLY | Two 501 routes; no constrained solver despite SciPy being available. |
| Presentation generation | INTEGRATION_ONLY | Two 501 routes; unsupported standalone builder is outside the API/CLI. |
| Streamlit companion | NOT_IMPLEMENTED | No application, dependency, smoke test, or runbook. |
| Static share site | NOT_IMPLEMENTED | No approved-snapshot builder or output. |

The standalone presentation builder hard-codes a user-specific absolute path, relies on an undeclared artifact tool, and is not reachable through the documented CLI. The README advertises a presentation export format that the parser does not accept.

## Artifact and interoperability audit

The existing release baseline contains 19 files under `outputs/` (approximately 15 MB) and 93 under `exports/` (approximately 5.9 MB). All primary artifacts retain the retired brand. No required current nAIM artifact exists.

All ZIP archives and both Office files pass compressed-package integrity checks.

### Excel

- 13 sheets, all rendered.
- 26 uniquely named tables and five native charts.
- No reported formula-error matches; reconciliation PASS.
- No freeze panes, defined names, or useful core/custom properties.
- Supplied VBA expects missing workbook names and tables, so it is not compatible with the delivered workbook.

Classification: structurally **VERIFIED_WORKING**, usability and macro compatibility **WORKING_BUT_INCOMPLETE**.

### PowerPoint

- 12 slides, all rendered, with notes on 12/12, source blocks, and four native charts.
- Representative slides are visually clean.
- Retired branding appears in every slide and notes XML file.
- Core title is generic; application metadata incorrectly says zero slides and zero notes.
- The alleged montage is only a rendering of slide 1.
- No explicit clipping/overlap validation result exists.
- Helvetica Neue is not embedded; Windows substitution is untested.

Classification: structurally **VERIFIED_WORKING**, release metadata/cross-platform/public branding **WORKING_BUT_INCOMPLETE**.

### Power BI, Tableau, SAS, and VBA/VBScript

- Power BI is a 12-file flat-snapshot enablement package with DAX, relationships, page specs, and reconciliation data. It is not a PBIP/TMDL project and has a reporting-period conflict. **INTEGRATION_ONLY**.
- Tableau contains CSVs, relationships, parameter guidance, and an unchecked build list. There is no Hyper or workbook, and several documented calculations require absent raw columns. **DOCUMENTATION_ONLY/INTEGRATION_ONLY**.
- SAS contains seven unexecuted source programs and CSV inputs; no SAS dataset or generated result exists. **INTEGRATION_ONLY**.
- VBA/VBScript is source-only and unexecuted. VBA is incompatible with the workbook; the VBScript containment check is prefix-based and vulnerable to sibling-prefix traversal. **INTEGRATION_ONLY/SECURITY_DEFECT**.

No `.hyper`, `.pbix`, `.pbip`, `.tmdl`, `.twb`, `.twbx`, `.sas7bdat`, `.xlsm`, PDF carousel, GIF, or MP4 is present.

### Provenance and packaging

- No `outputs/manifests/` or per-artifact provenance manifests exist.
- Workbook/deck validation evidence hashes do not equal the final artifact hashes.
- Validation JSONs contain exact workstation paths and are embedded in source/interoperability ZIPs.
- The source ZIP otherwise excludes actual environment secrets, dependency trees, and generated raw/ground-truth data.
- The packager cannot produce the required standalone Tableau, SAS, LinkedIn, screenshots, share-site, manifest, or nAIM release set.

## Social and public-readiness audit

The existing social preview is 1672×941, not 1200×627. There is no square image, carousel PDF, editable carousel source, summaries, or alt text.

It is analytically unsafe: it shows `+31 bps`, mix `+18`, performance `+9`, macro `+4`, and a 2022–2025 chart, while current governed evidence is `+311.415 bps`, mix `+4.434`, within-segment performance `+306.981`, and January 2024–December 2025. It also displays the malformed phrase “DO PASS.” It must not be renamed or reused.

The screenshots archive contains seven retired-brand images and no alt-text manifest or curated demo capture. Browser metadata names an unsubstantiated Sites URL. A hosted frontend would default to localhost and fall back to demo data if the API were absent.

`.openai/hosting.json` contains null D1 and R2 values with no project ID. The Site has not been published.

## Branding and namespace inventory

The retired brand remains in active web metadata, header/footer, UI copy, demo data, API title/root/product metadata, commentary identifiers, Python package, npm package, environment variables, containers, volume names, Make targets, release scripts, tests, docs, public image assets, output filenames, and embedded Office XML.

Canonical migration targets are:

- Public product: `nAIM Portfolio Intelligence Workbench`
- Python namespace: `naim_risk`
- CLI: `naim`
- Environment prefix: `NAIM_`
- Browser API variable: `NEXT_PUBLIC_NAIM_API_URL`
- Docker services: `naim-api`, `naim-web`
- Deployment slug: `naim-portfolio-intelligence-workbench`

Legacy references may remain only in this migration evidence, isolated archives/manifests, deprecation shims, or explicit compatibility comments.

## Startup failure diagnosis

The terminal transcript shows commands executed from the user home directory. That explains the missing `.env.example`, `scripts/run_pipeline.py`, and Make target. The requested `python3.12` executable is not on the system path, but the project-local `.venv/bin/python` is Python 3.12.13. The system `python3` is older than the project requirement. Docker is unavailable.

The README must explicitly begin with changing into the repository folder, then use a discovered compatible interpreter to create `.venv`, and thereafter use `.venv/bin/python`. The Makefile must not silently default to the incompatible system interpreter.

## Prioritized continuation gates

1. Enforce canonical nAIM branding and compatibility boundaries with regression tests.
2. Add a machine-readable capability registry and make UI/API claims derive from it.
3. Replace hybrid source behavior with strict LIVE, DEMO, OFFLINE_SNAPSHOT, and UNAVAILABLE modes.
4. Extend point-in-time bounds and add future-row invariance tests before new analytical claims.
5. Add durable, versioned, soft-deletable workflow persistence with restart evidence.
6. Add configurable disabled/demo/OIDC authentication and backend role enforcement.
7. Replace all eight 501 operations with supported implementations or explicit non-live registry status; no decorative route counts.
8. Add Market Risk and Volatility Lab and selected advanced methods only with reproducible evidence.
9. Correct documentation overclaims, remove absolute paths, add per-artifact provenance, and regenerate all public artifacts from governed values.
10. Run browser, Office, security, dependency, performance, contract, container/static, and hosted deployment QA before claiming completion.

## Baseline disposition

Preserve the analytical core, deterministic data generator, data-quality gate, root-cause reconciliation, existing API service structure, artifact source material, and validated run evidence. Replace or harden the unsafe live/demo boundary, process-local mutable state, anonymous mutation surface, 501 integrations, mocked interactions, public branding, and ungoverned artifact claims.
