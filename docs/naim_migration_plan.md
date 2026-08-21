# nAIM migration plan

## Objective

Migrate the working legacy application to the public identity **nAIM Portfolio Intelligence Workbench**, pronounced “name,” while preserving analytical behavior and a reversible evidence trail. AIM means **All Is Mine**. The public tagline is **Name the movement. Own the evidence.**

## Protected baseline

The pre-migration checksums, runtime versions, run pointer, and artifact inventory are recorded in `outputs/migration/before_migration_manifest.json`. The supplied workspace is not a Git repository, so no migration tag can be created. The manifest is the immutable comparison anchor.

Historical artifacts remain untouched until replacement artifacts pass validation. They may then be isolated under a clearly marked legacy archive; they must not be presented as current nAIM outputs.

## Migration sequence

1. Rerun the full existing Python, API, frontend, model-registry, pipeline, benchmark, and artifact checks before modifying product behavior.
2. Record route, API, capability, data-mode, persistence, authentication, quantitative-method, security, and artifact gaps in `docs/continuation_audit.md`.
3. Introduce the `naim_risk` Python namespace, `naim` CLI, `NAIM_` environment variables, nAIM service names, and the nAIM deployment slug. Retain narrowly scoped deprecated compatibility shims only where required.
4. Add automated regression checks that reject the retired brand in active public surfaces while allowing this migration record, compatibility comments, and the isolated legacy manifest.
5. Add the machine-readable capability registry, strict data-mode boundaries, point-in-time guards, durable workflow state, and role-enforced authentication before expanding analytical scope.
6. Replace explicit HTTP 501 placeholders for onboarding, portfolio optimisation, and presentation export with tested implementations.
7. Implement and validate the market-risk, volatility, advanced-statistics, workspace, export, sharing, and optional-provider slices in priority order. Anything unavailable remains explicit in the capability registry.
8. Regenerate all public artifacts under nAIM names; validate calculations, provenance, links, formulas, layouts, accessibility, and cross-artifact consistency.
9. Run production builds, API-contract generation, security and performance checks, browser breakpoints, and deployment smoke tests. Publish through the configured Sites workflow only after the hosted build passes.
10. Produce `outputs/nAIM_Release_Evidence.json` and `outputs/nAIM_Release_Validation.md` from the new verification run. No historical metric is copied forward without fresh evidence.

## Compatibility window

- Canonical package: `naim_risk`.
- Canonical CLI: `naim`.
- Canonical environment prefix: `NAIM_`.
- Canonical web client variable: `NEXT_PUBLIC_NAIM_API_URL`.
- Legacy imports and environment names, if retained, are deprecated adapters. They cannot appear in public UI, current artifact titles, deployment names, or user-facing documentation.
- Compatibility warnings must identify the replacement and planned removal path.

## Rollback approach

Because there is no source-control history in the supplied folder, rollback is file-manifest based:

1. Stop running services and preserve any new state database or export jobs.
2. Compare the workspace against `outputs/migration/before_migration_manifest.json`.
3. Restore the original supplied workspace from its external source or delivery archive, rather than deleting or overwriting files in place.
4. Verify every protected artifact and control-file SHA-256 checksum.
5. Repoint `data/manifests/latest.json` to the captured baseline run only after its referenced manifest checksum matches.

This procedure deliberately avoids destructive reset commands and does not claim that untracked source files can be reconstructed from artifact hashes alone. A source archive or an initialized Git repository is required for complete rollback.

## Completion gate

The migration is complete only when current public assets contain no retired branding, all LIVE capabilities have executable evidence, no material route returns a placeholder response, strict mode and time-boundary tests pass, durable workflow state survives restart, browser and artifact QA pass, and the published Site matches the validated local build. Any unmet item remains documented as integration-only, documented, disabled, or not implemented.
