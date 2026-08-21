# Release evidence protocol

nAIM uses a two-stage, one-way release protocol. This prevents the readiness workbook or a
package that contains release evidence from changing the evidence that made the release decision.

## Stage 1: immutable core decision

`scripts/generate_release_evidence.py --phase core` reads only pre-decision evidence and writes:

- `outputs/nAIM_Release_Core_Evidence.json`;
- `outputs/nAIM_Release_Validation.md`; and
- `outputs/nAIM_Release_Readiness_Matrix.json`.

The readiness workbook, research package, GitHub package, and screenshots package may consume
`nAIM_Release_Core_Evidence.json`. The core evidence never consumes those post-decision artifacts.
A passing core file is immutable: another core invocation fails closed unless the operator uses
the explicit `--replace-core` invalidation switch. Normal completion continues with `--phase final`.

The core artifact gate contains exactly:

1. source package;
2. Excel workbench;
3. PowerPoint review;
4. Tableau Desktop package;
5. Power BI Desktop package;
6. SAS compatibility package; and
7. LinkedIn showcase package.

Readiness, research, GitHub, and screenshots are intentionally excluded from the core decision.

## Stage 2: final verification envelope

`scripts/generate_release_evidence.py --phase final` writes only:

- `outputs/nAIM_Release_Evidence.json`.

No release artifact may consume this final envelope. It verifies the unchanged core evidence, all
eleven release artifacts and manifests, a fresh final reconciliation, and real browser-derived UI
evidence. Its `verification_order` is deterministic: core evidence, then the seven core artifacts,
then readiness, research, GitHub, and screenshots.

The final reconciliation is written to a separate file:

```text
outputs/validation/final_cross_artifact_reconciliation.json
```

This is deliberate. Reusing or overwriting the core reconciliation would invalidate the test-run
binding and immutable core source fingerprint. At final verification, `ui_snapshot` must be `PASS`
with a present, independently rehashed artifact. Only `streamlit_snapshot` may remain `INCOMPLETE`,
as the explicitly documented optional companion-runtime boundary. An empty or fabricated UI
channel cannot pass.

## Persisted release-test evidence

`scripts/run_release_tests.py` is the only canonical producer of
`outputs/validation/test_results.json`. A release-valid invocation must contain:

- top-level `status: PASS` and `release_gate_passed: true`;
- `selected_suites` exactly equal to `backend`, `frontend`, and `e2e` in that order;
- exactly one uniquely named suite for each category, each with `status: PASS`, `exit_code: 0`,
  `failed: 0`, and a positive passed count;
- same-invocation JUnit XML and JSON coverage records with path, byte size, SHA-256, invocation ID,
  modification time inside the recorded invocation window, and `generated_in_invocation: true`; and
- current bindings for the authored source tree, package lock, feature configuration, canonical
  evidence, canonical run manifest, OpenAPI contract and validation, and core reconciliation.

The evidence consumer independently rehashes every binding. It never reads `.coverage`, never
accepts an old JUnit file, and never promotes an unselected or duplicate suite. The complete test
invocation also becomes stale after 24 hours.

## Reconciliation contract

The core reconciliation must contain the following channel IDs exactly once and in stable order:

```text
api_service_evidence
ui_snapshot
excel_workbook
powerpoint_review
tableau_hyper
power_bi_validation
streamlit_snapshot
static_share_site
linkedin_carousel
```

All channels remain explicitly `required`. At the core-decision phase only, `ui_snapshot` may be
`INCOMPLETE` because screenshots are post-decision. `streamlit_snapshot` may also be `INCOMPLETE`
because it is an optional external companion runtime. These are the complete allowlist; no unknown
channel or status is inferred. Every core channel must be `PASS`, contain required checks and
artifact records, and have internally consistent expected/actual outcomes. Every recorded artifact
is independently rehashed and must not have been modified after reconciliation. Evidence older than
24 hours is stale.

## Manifest contract

Every expected release artifact has exactly one canonical manifest under `outputs/manifests/`.
The 24 Section 130.2 fields are mandatory. Provenance values cannot be null or empty; evidence IDs,
dependencies and validation tests must be non-empty; source inputs must be present and hashed.
Declared dependencies and validation-evidence paths must exist inside the repository. File name,
size, top-level SHA-256 and nested artifact record must match the current artifact bytes.

Validation statuses are strict by runtime classification:

- Power BI and SAS packages: `STATIC_VALIDATION_PASS` only;
- every other release artifact: `PASS` only.

`PARTIAL`, arbitrary strings, nulls and generic non-failure statuses never pass. Dataset,
configuration, metric-registry, run/snapshot and evidence IDs must match canonical lineage.
Post-decision manifests must depend on `outputs/nAIM_Release_Core_Evidence.json` and include its
current hash when it is represented as a source-input record.

## Contract, security and performance evidence

The OpenAPI validator's declared contract is reread and rehashed. A passing status with a stale
contract hash, missing operation counts, duplicate/missing operation IDs, errors, or declared HTTP
501 responses fails.

The npm audit summary must record a zero-advisory pass and bind the current `package-lock.json`
SHA-256. The security result may honestly remain `PARTIAL` only when local controls pass and the
uncompleted external boundaries are explicitly listed; the resulting gate is
`PASS_WITH_EXTERNAL_BOUNDARIES`, not an invented complete security claim. Dependency evidence older
than two days is stale.

Performance evidence must be a fresh-run schema-valid report no older than 14 days. Requested and
reported profiles must match, the default profile is mandatory, and every measured operation needs
complete median, p95 and sample evidence. The only allowed external operations are Hyper generation
for `fast`, `default`, and `medium`; each needs a reason and rerun requirement. Completeness must
exactly enumerate those operations. Other external-operation labels fail closed.

## Exact release sequence

Run this only after derivative writers have stopped and core artifact bytes/manifests are final:

```bash
PYTHONPATH=src .venv/bin/python scripts/reconcile_release_artifacts.py
PYTHONPATH=src .venv/bin/python scripts/run_release_tests.py
PYTHONPATH=src .venv/bin/python scripts/generate_release_evidence.py --phase core
```

Then build the readiness workbook, research, GitHub and screenshots packages from
`outputs/nAIM_Release_Core_Evidence.json`, and create their core-bound manifests. Capture the real
browser UI snapshot and run the separate final reconciliation:

```bash
PYTHONPATH=src .venv/bin/python scripts/reconcile_release_artifacts.py \
  --output outputs/validation/final_cross_artifact_reconciliation.json
PYTHONPATH=src .venv/bin/python scripts/generate_release_evidence.py --phase final
```

Every command exits zero only when its own gate passes. `--suite backend|frontend|e2e` remains a
scoped diagnostic option for the test runner, but a scoped invocation is never release-valid.
`--dry-run` prints commands and endpoints without writing evidence. Use `--replace-core` only when
the prior passing core decision is intentionally invalidated and the entire sequence will be rerun.
