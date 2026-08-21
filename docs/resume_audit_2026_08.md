# nAIM resume audit - 2026-08

Audit captured: 2026-08-08T09:37:16Z  
Repository: `google-drive-plugin-google-drive-openai-3`  
Purpose: recover the exact interrupted state before correcting or extending the product.

## Executive finding

The project is recoverable and the principal analytical baseline is intact. The canonical
nAIM evidence snapshot is current, synthetic, publication-eligible under its local data-quality
gate, and tied to deterministic run `default-73421-6006e471387a`. The current release is not
ready: the cross-artifact reconciliation file predates the refreshed canonical evidence, release
manifests and several required native artifacts are missing, and the SQLite bootstrap path still
mixes SQLAlchemy `create_all()` with Alembic migrations.

No source-control history is available in this supplied folder. It is not a Git worktree, so
recovery relies on repository checkpoints, machine-readable validation files, artifact hashes,
and focused test reruns. Existing outputs and user work have not been deleted or reset.

Three numbered duplicate files were also recovered: an obsolete 51-line workbook-inspection
helper, an older Power BI setup note, and an older favicon. Their hashes differ from the canonical
files and their contents are superseded. They are excluded from release evidence and will be
archived or removed only after the canonical rebuild confirms no active reference depends on them.

## Recovered environment

| Control | Recovered state |
|---|---|
| Python | 3.12.13 in the project-local `.venv` |
| Node | 22.17.0 |
| Local ports | 3000 and 8000 available during the audit |
| Configuration template | `.env.example` present |
| Docker | Not installed in the previously supplied terminal environment; not required for the core localhost path |
| Git | No `.git` worktree found |
| Hosting declaration | `.openai/hosting.json` present; hosted publication has not been claimed |

## Canonical analytical evidence

Controlling file: `exports/validation/interop_evidence_snapshot.json`

| Field | Recovered value |
|---|---|
| Product | nAIM Portfolio Intelligence Workbench |
| Evidence ID | `NAIM-default-73421-6006e471387a` |
| Run ID | `default-73421-6006e471387a` |
| Configuration hash | `6006e471387a89e4e8bf7cca3e9f9e398f949b1acb00daa0531b25bc10436a9d` |
| Metric-registry version | `1.0.0` |
| Synthetic data | true |
| Data-quality status | PASS |
| Account-month rows | 513,923 |
| File SHA-256 | `bb0e152f6ea19b0edf0151d35546ad3e38e4a831aacc47befbcafb764aa22358` |
| Embedded canonical payload hash | `f55b8d658a0ca00cefdf71d6de97ee4f2ecf71bdeba2b4f6669619361bbdc3a5` |

The governed headline remains the all-portfolio movement for 2025-08 versus 2025-07. Approved
basket `BASKET-001` is a secondary control reference and must not be presented as the population
used for the headline.

## Recovered release artifacts

| Artifact | Native QA | File SHA-256 | Recovery note |
|---|---:|---|---|
| `outputs/nAIM_Portfolio_Intelligence_Workbench.xlsx` | PASS, 17 rendered sheets, zero formula-error matches | `f9beddbc3be7394f4618b84fa43455cb35b98405dc1f33da1c3bae714350ae78` | Validated before the final canonical evidence refresh; must be reconciled and manifested again |
| `outputs/nAIM_Portfolio_Intelligence_Review.pptx` | PASS, 7/7 slides and notes rendered/inspected | `168640d46608e2dcbafab16f972c45ff25aeb210dbb88bd4dfd24762c21ca5fd` | Correct 2025-08/2025-07 scope, but requires regeneration/reconciliation after metadata changes |
| `outputs/powerbi/nAIM.PowerBIProject` | Static project present | n/a | Generator contains the intended provenance expansion; output project has not yet been rebuilt from the refreshed evidence |
| `outputs/share_site` | Static snapshot present | n/a | Downstream of older evidence; rebuild required |
| Tableau/SAS source packs | Present | n/a | Desktop runtimes remain external validation gates |

Retired pre-nAIM artifacts remain in `outputs/` and `exports/validation/` as historical residue. They
must not be included in the final nAIM release package or public surface. Removal or archival will
only occur through an explicit, recoverable cleanup step after the nAIM package is green.

## Reconciliation state

`outputs/validation/cross_artifact_reconciliation.json` currently reports `FAIL` and
`release_allowed: false`. Its canonical story still contains the former product/evidence ID
and its embedded canonical file hash differs from the current nAIM snapshot. Therefore the file is
stale evidence of an earlier release gate, not proof that the refreshed canonical numbers
disagree. It must be regenerated only after every derivative is rebuilt.

Known unresolved release gates recovered from that file:

- final UI snapshot and Streamlit/static snapshot evidence;
- release manifests for the Excel, PowerPoint, and static site artifacts;
- Excel-to-PowerPoint reconciliation recorded in the presentation manifest;
- Tableau Hyper artifact/runtime classification;
- rebuilt Power BI provenance;
- complete LinkedIn carousel, PDF, file ledger, and provenance;
- final cross-channel release check.

## API and capability truth

- OpenAPI contains 104 paths and 110 operations, including 109 `/api/v1` operations.
- The capability registry validates 63 entries: 40 LIVE, 13 INTEGRATION_ONLY, 2 DOCUMENTED,
  and 8 NOT_IMPLEMENTED.
- Public-brand scanning passes with four explicit compatibility exceptions.
- Frontend contract generation is current; a new typecheck was started during recovery and its
  contract check and typecheck both passed.
- The recovered artifact-manifest, reconciler, Power BI, and database CLI unit slice passed
  20/20 tests. This is focused recovery evidence, not the final full-suite result.

These counts describe the recovered repository. They are not a substitute for the final full
release suite and will be recalculated after the new vertical slices.

## SQLite and lifecycle defect

The Alembic base migration creates the durable workflow, identity, revocation, and audit tables.
`WorkflowStore.initialize_schema()` also invokes `Base.metadata.create_all()`. The service creates
the store through this bootstrap path, while `naim db upgrade` separately runs Alembic. A database
that was first bootstrapped by the service can therefore contain tables without an Alembic
revision; a later migration tries to create the same tables and raises errors such as
`workflow_object already exists`.

Required correction:

1. stop treating `create_all()` and Alembic as interchangeable production lifecycle paths;
2. inspect before changing a local SQLite file;
3. create a timestamped backup before repair;
4. stamp only when the existing schema is structurally compatible with the migration;
5. upgrade normally after a safe stamp;
6. refuse destructive repair for unknown or incompatible schemas;
7. expose `make db-status`, `make db-repair`, and `make db-upgrade` with focused tests.

## Recovery priorities

1. Repair SQLite migration ownership and the one-command local lifecycle.
2. Rebuild every derivative from the current canonical evidence.
3. Generate complete release manifests and rerun cross-artifact reconciliation.
4. Produce the release evidence/validation pair and review packet.
5. Only after those gates are stable, implement the Monthly Portfolio Review Compiler as the first
   semantic vertical slice.

## Current release decision

**BLOCKED - release correctness work is in progress.**

This is a controlled block, not a loss of work. The canonical evidence and principal native Office
artifacts are intact; the blocking work is migration safety, derivative freshness, manifest
completeness, and cross-tool reconciliation.
