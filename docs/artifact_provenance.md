# Artifact provenance

Every current nAIM release artifact must have a portable JSON manifest under `outputs/manifests/`. A manifest is generated only after the artifact itself exists and has passed its format-specific checks.

The manifest records:

- exact product and schema version;
- repository-relative artifact path, byte size, type, and SHA-256 checksum;
- UTC build time and deterministic build ID;
- creator and tool versions;
- source snapshot identifier;
- strict data mode and reporting period;
- dataset, configuration, model, API, and builder versions, or an explicit reason when one is not applicable;
- repository-relative source inputs with checksums;
- validation-evidence paths;
- caveats.

Absolute workstation paths, environment files, private keys, and artifacts outside `outputs/` are rejected. Manifest files cannot recursively register themselves as release artifacts.

The deterministic build ID excludes wall-clock build time. The same artifact bytes and governed context therefore produce the same build ID, while the manifest still records when a particular package was assembled.

Example:

```text
.venv/bin/python scripts/generate_artifact_manifests.py \
  outputs/nAIM_Portfolio_Intelligence_Workbench.xlsx \
  --source-snapshot-id default-73421-6006e471387a \
  --data-mode OFFLINE_SNAPSHOT \
  --reporting-period 2025-08 \
  --dataset-hash <sha256> \
  --configuration-hash <sha256> \
  --model-version-reason "No model is used by this artifact" \
  --api-version 1.0.0 \
  --script-version 1.0.0 \
  --source-input data/manifests/default-73421-6006e471387a/run_manifest.json \
  --validation-evidence outputs/nAIM_Release_Evidence.json
```

Release packaging must verify the manifest checksum against the final artifact after all metadata and layout changes. A mismatch invalidates the package.
