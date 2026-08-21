# Cycle-safe final release packages

`scripts/build_final_release_packages.py` owns only these exact archives:

- `outputs/nAIM_Portfolio_Intelligence_Workbench_Source.zip`
- `outputs/nAIM_Research_Package.zip`
- `outputs/nAIM_GitHub_Release_Package.zip`
- `outputs/nAIM_Screenshots.zip`

The builder fails closed. It writes a temporary archive, validates it, and atomically publishes
the target only after all checks pass. `--dry-run` performs the prerequisite, content, checksum,
secret, and embedded-archive checks without writing output bytes.

## Shared archive contract

Every archive has one top-level product folder and one internal `PACKAGE_CONTENTS.json`. The
ledger declares every other member's portable archive path, SHA-256, byte size, and source
classification. The validator rejects duplicate or undeclared members and recalculates every
hash and size. ZIP members are written in lexical order with the fixed timestamp
`1980-01-01T00:00:00Z`, fixed regular-file permissions, and deterministic compression settings.

The packages never contain their own outer ZIP or sidecar manifest. They also never contain the
final `nAIM_Release_Evidence.json`, because that evidence is a post-build decision artifact and
including it would create a checksum cycle. The release validation report is also left outside
these archives because its artifact inventory is post-build state.

The validator rejects absolute or traversing archive paths, symlinks, environment/credential
files, high-confidence secrets, runtime environments, dependency trees, caches, generated build
trees, numbered stale duplicates such as `measures 2.dax`, and paths containing the retired
product name.

The Research, Screenshots, and GitHub ledgers each declare
`outputs/nAIM_Release_Core_Evidence.json` as a dependency with its exact SHA-256 and byte size.
The same immutable file is included under the package's `evidence/` folder, and validation proves
that the dependency checksum and included content checksum match.

## Package contents

### Source

The Source archive contains authored application/backend code, configuration, schemas, tests,
documentation, migrations, build scripts, interoperability source, and public application
assets. It excludes the repository's generated `data`, `outputs`, `work`, `dist`, dependency,
cache, and environment trees.

Three builder families are deliberately relocated to `release-builders/` inside the archive:

- the readiness workbook builder from `work/artifacts/readiness/build_readiness_matrix.mjs`;
- the authored Sites integration from `build/sites-vite-plugin.ts`;
- the maintained Office/carousel builder scripts from `.artifact-workbook/`.

The packaged `vite.config.ts` receives one deterministic import-path rewrite so the relocated
Sites builder remains executable. Both the packaged hash and original source hash are recorded
for this portable transformation.

### Research

The Research archive requires release readiness and the separate final cross-artifact
reconciliation to pass its fail-closed post-decision contract. Every required channel must pass;
only the explicitly documented Streamlit companion channel may remain `INCOMPLETE`. The builder
re-hashes every recorded reconciliation artifact before packaging. It contains Release Core
Evidence, the canonical evidence snapshot, final reconciliation evidence,
readiness JSON/workbook and workbook validation, methodology/security documentation, and any
available governed test, security, performance, Office, API, and interoperability validation
records. If the latest analytical run manifest exists, portable copies are included with local
absolute repository prefixes removed.

### Screenshots

The Screenshots archive is not produced from an unindexed folder. It requires
`outputs/screenshots/browser_capture_index.json` with this shape:

```json
{
  "schema_version": "1.0.0",
  "capture_kind": "REAL_BROWSER",
  "real_browser": true,
  "validation_status": "PASS",
  "browser": "Codex in-app browser",
  "captures": [
    {
      "view_id": "start-here",
      "file": "start-here-desktop.png",
      "real_browser": true,
      "validation_status": "PASS",
      "availability_state": "LIVE",
      "viewport": {"name": "desktop", "width": 1440, "height": 1000}
    }
  ]
}
```

Every capture file must be a unique relative PNG below `outputs/screenshots`, have a valid PNG
header, be at least 320 by 200 pixels, and meet the declared viewport dimensions. Every PNG on
disk must be declared, so stale screenshots block the package.

Desktop captures are mandatory for these exact `view_id` values:

- `start-here`, `why-naim`, `how-naim-works`, `use-case-library`
- `command-centre`, `trends`, `vintage`, `strategy`, `root-cause`
- `market-risk`, `advanced-statistics`, `partner`, `vendor`, `customer-membership`
- `investigations`, `data-quality`, `methodology`, `capability-status`
- `download-centre`, `instant-demo`

At least one indexed tablet capture and one indexed mobile capture are also required. An
`UNAVAILABLE`, `ERROR`, or `STALE` availability state blocks packaging.

### GitHub release envelope

The GitHub archive requires a passing readiness decision and the same validated final
reconciliation contract (including the explicit optional Streamlit boundary). It contains
the deterministic Source, Research, and Screenshots archives; the validated workbook and review
deck; the Tableau, Power BI, SAS, and LinkedIn packages; direct Core/canonical/reconciliation
evidence; readiness outputs; and the selected user/reviewer documentation. It never contains its
own ZIP or manifest.

## Final command order

Run the full fail-closed validation without writing archives:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/build_final_release_packages.py \
  --package source \
  --package research \
  --package screenshots \
  --package github \
  --dry-run
```

After all inputs are frozen, build in the same topological order:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/build_final_release_packages.py \
  --package source \
  --package research \
  --package screenshots \
  --package github
```

Focused verification:

```bash
.venv/bin/ruff check \
  scripts/build_final_release_packages.py \
  tests/unit/test_build_final_release_packages.py
PYTHONPATH=src:. .venv/bin/pytest -q \
  tests/unit/test_build_final_release_packages.py
```
