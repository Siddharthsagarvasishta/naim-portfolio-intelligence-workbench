#!/usr/bin/env python3
"""Create portable provenance manifests for nAIM release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PRODUCT_NAME = "nAIM Portfolio Intelligence Workbench"
SCHEMA_VERSION = "2.0.0"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPOSITORY_ROOT / "outputs"
DEFAULT_MANIFEST_ROOT = DEFAULT_OUTPUT_ROOT / "manifests"
DATA_MODES = {"LIVE", "DEMO", "OFFLINE_SNAPSHOT", "UNAVAILABLE"}


@dataclass(frozen=True)
class ProvenanceValue:
    """A provenance value or an explicit explanation for its absence."""

    value: str | None
    reason: str | None = None

    def validate(self, name: str) -> None:
        if self.value is None and not self.reason:
            raise ValueError(f"{name} requires a value or a reason")
        if self.value is not None and self.reason:
            raise ValueError(f"{name} cannot contain both a value and a reason")


@dataclass(frozen=True)
class ManifestContext:
    """Governed context shared by one or more generated artifact manifests."""

    source_snapshot_id: str
    data_mode: str
    reporting_period: str
    comparison_period: str
    dataset_profile: str
    dataset_hash: ProvenanceValue
    configuration_hash: ProvenanceValue
    model_version: ProvenanceValue
    api_version: ProvenanceValue
    script_version: ProvenanceValue
    metric_registry_version: str
    filter_scope: dict[str, Any]
    evidence_ids: tuple[str, ...]
    data_quality_result: str
    synthetic_data: bool
    validation_status: str
    creator: str = "nAIM release pipeline"
    source_workspace: str = "all_portfolio_control"
    artifact_version: str = "1.0.0"
    dependencies: tuple[str, ...] = ()
    validation_tests: tuple[str, ...] = ()
    tool_versions: dict[str, str] = field(default_factory=dict)
    validation_evidence: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.source_snapshot_id.strip():
            raise ValueError("source_snapshot_id is required")
        if self.data_mode not in DATA_MODES:
            raise ValueError(f"data_mode must be one of {sorted(DATA_MODES)}")
        if not self.reporting_period.strip():
            raise ValueError("reporting_period is required")
        if not self.comparison_period.strip():
            raise ValueError("comparison_period is required")
        if not self.dataset_profile.strip():
            raise ValueError("dataset_profile is required")
        if not self.metric_registry_version.strip():
            raise ValueError("metric_registry_version is required")
        if not self.filter_scope:
            raise ValueError("filter_scope is required")
        if not self.evidence_ids or any(not item.strip() for item in self.evidence_ids):
            raise ValueError("evidence_ids requires at least one non-empty identifier")
        if not self.data_quality_result.strip():
            raise ValueError("data_quality_result is required")
        if self.validation_status not in {
            "PASS",
            "PARTIAL",
            "FAIL",
            "STATIC_VALIDATION_PASS",
            "NOT_EXECUTABLE_LOCALLY",
        }:
            raise ValueError("validation_status is not a governed release status")
        if not isinstance(self.synthetic_data, bool):
            raise ValueError("synthetic_data must be a boolean")
        if not self.source_workspace.strip():
            raise ValueError("source_workspace is required")
        if not self.artifact_version.strip():
            raise ValueError("artifact_version is required")
        for name in (
            "dataset_hash",
            "configuration_hash",
            "model_version",
            "api_version",
            "script_version",
        ):
            getattr(self, name).validate(name)


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest for a file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_path(path: Path, repository_root: Path) -> str:
    """Return a repository-relative POSIX path after containment validation."""

    resolved = path.resolve()
    root = repository_root.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Path is outside the repository boundary: {path}")
    return resolved.relative_to(root).as_posix()


def validate_artifact_path(path: Path, output_root: Path) -> Path:
    """Require an existing regular artifact below the governed output root."""

    resolved = path.resolve()
    root = output_root.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Artifact is outside the output boundary: {path}")
    if not resolved.exists():
        raise FileNotFoundError(path)
    if not resolved.is_file():
        raise ValueError(f"Artifact must be a regular file: {path}")
    if (root / "manifests").resolve() in resolved.parents:
        raise ValueError("Manifest files cannot be registered as release artifacts")
    return resolved


def _source_records(source_inputs: list[Path], repository_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source in source_inputs:
        resolved = source.resolve()
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(source)
        relative = portable_path(resolved, repository_root)
        if Path(relative).name == ".env" or Path(relative).suffix.lower() in {".pem", ".key"}:
            raise ValueError(f"Secret-bearing input is not allowed in provenance: {relative}")
        records.append(
            {
                "path": relative,
                "bytes": resolved.stat().st_size,
                "sha256": sha256_file(resolved),
            }
        )
    return sorted(records, key=lambda item: item["path"])


def _deterministic_build_id(payload: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in payload.items()
        if key not in {"created_at", "built_at_utc", "artifact_id", "build_id"}
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"NAIM-{hashlib.sha256(encoded).hexdigest()[:20].upper()}"


def artifact_type(path: Path) -> str:
    """Return a stable release-artifact classification from the physical file."""

    return {
        ".xlsx": "EXCEL_WORKBOOK",
        ".pptx": "POWERPOINT_PRESENTATION",
        ".hyper": "TABLEAU_HYPER_EXTRACT",
        ".zip": "ZIP_PACKAGE",
        ".csv": "CSV_EXTRACT",
        ".parquet": "PARQUET_EXTRACT",
        ".json": "JSON_EVIDENCE",
        ".html": "HTML_ARTIFACT",
        ".pdf": "PDF_DOCUMENT",
        ".png": "PNG_IMAGE",
    }.get(path.suffix.lower(), "BINARY_ARTIFACT")


def build_manifest(
    artifact: Path,
    context: ManifestContext,
    *,
    source_inputs: list[Path] | None = None,
    repository_root: Path = REPOSITORY_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    built_at: datetime | None = None,
) -> dict[str, Any]:
    """Build one validated, portable manifest without writing it."""

    context.validate()
    artifact = validate_artifact_path(artifact, output_root)
    artifact_relative = portable_path(artifact, repository_root)
    evidence = []
    for item in context.validation_evidence:
        evidence_path = (repository_root / item).resolve()
        evidence.append(portable_path(evidence_path, repository_root))

    created_at = (built_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    sources = _source_records(source_inputs or [], repository_root)
    validation_evidence = sorted(set(evidence))
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "product": PRODUCT_NAME,
        "created_at": created_at,
        "built_at_utc": created_at,
        "artifact_type": artifact_type(artifact),
        "artifact_version": context.artifact_version,
        "created_by_component": context.creator,
        "source_workspace": context.source_workspace,
        "creator": context.creator,
        "tool_versions": {
            "python": platform.python_version(),
            "manifest_builder": SCHEMA_VERSION,
            **dict(sorted(context.tool_versions.items())),
        },
        "artifact": {
            "path": artifact_relative,
            "filename": artifact.name,
            "type": artifact.suffix.lower().lstrip(".") or "binary",
            "bytes": artifact.stat().st_size,
            "sha256": sha256_file(artifact),
        },
        "source_snapshot_id": context.source_snapshot_id,
        "data_mode": context.data_mode,
        "reporting_period": context.reporting_period,
        "comparison_period": context.comparison_period,
        "dataset_profile": context.dataset_profile,
        "metric_registry_version": context.metric_registry_version,
        "filter_scope": context.filter_scope,
        "evidence_ids": list(context.evidence_ids),
        "data_quality_result": context.data_quality_result,
        "data_quality_status": context.data_quality_result,
        "synthetic_data": context.synthetic_data,
        "synthetic_data_flag": context.synthetic_data,
        "dataset_hash": context.dataset_hash.value,
        "configuration_hash": context.configuration_hash.value,
        "code_version": context.script_version.value,
        "file_name": artifact.name,
        "file_size": artifact.stat().st_size,
        "sha256": sha256_file(artifact),
        "dependencies": [*context.dependencies, *[item["path"] for item in sources]],
        "validation_status": context.validation_status,
        "validation_tests": [*context.validation_tests, *validation_evidence],
        "known_limitations": list(context.caveats),
        "versions": {
            "dataset_hash": asdict(context.dataset_hash),
            "configuration_hash": asdict(context.configuration_hash),
            "model_version": asdict(context.model_version),
            "api_version": asdict(context.api_version),
            "script_version": asdict(context.script_version),
        },
        "source_inputs": sources,
        "validation_evidence": validation_evidence,
        "caveats": list(context.caveats),
    }
    payload["build_id"] = _deterministic_build_id(payload)
    payload["artifact_id"] = payload["build_id"]
    return payload


def manifest_filename(artifact: Path, output_root: Path) -> str:
    relative = artifact.resolve().relative_to(output_root.resolve()).as_posix()
    safe = "__".join(Path(relative).parts).replace(" ", "_")
    return f"{safe}.manifest.json"


def write_manifest(
    payload: dict[str, Any],
    artifact: Path,
    *,
    manifest_root: Path = DEFAULT_MANIFEST_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    manifest_root.mkdir(parents=True, exist_ok=True)
    if not manifest_root.resolve().is_relative_to(output_root.resolve()):
        raise ValueError("Manifest output must remain below the output boundary")
    target = manifest_root / manifest_filename(artifact, output_root)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def _value(value: str | None, reason: str | None, name: str) -> ProvenanceValue:
    result = ProvenanceValue(value=value, reason=reason)
    result.validate(name)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="+", type=Path)
    parser.add_argument("--source-snapshot-id", required=True)
    parser.add_argument("--data-mode", required=True, choices=sorted(DATA_MODES))
    parser.add_argument("--reporting-period", required=True)
    parser.add_argument("--comparison-period", required=True)
    parser.add_argument("--dataset-profile", required=True)
    parser.add_argument("--metric-registry-version", required=True)
    parser.add_argument("--filter-scope-json", required=True)
    parser.add_argument("--evidence-id", action="append", required=True)
    parser.add_argument("--data-quality-result", required=True)
    parser.add_argument(
        "--validation-status",
        required=True,
        choices=(
            "PASS",
            "PARTIAL",
            "FAIL",
            "STATIC_VALIDATION_PASS",
            "NOT_EXECUTABLE_LOCALLY",
        ),
    )
    parser.add_argument("--synthetic-data", choices=("true", "false"), required=True)
    for name in ("dataset-hash", "configuration-hash", "model-version", "api-version", "script-version"):
        parser.add_argument(f"--{name}")
        parser.add_argument(f"--{name}-reason")
    parser.add_argument("--source-input", action="append", type=Path, default=[])
    parser.add_argument("--source-workspace", default="all_portfolio_control")
    parser.add_argument("--artifact-version", default="1.0.0")
    parser.add_argument("--dependency", action="append", default=[])
    parser.add_argument("--validation-test", action="append", default=[])
    parser.add_argument("--validation-evidence", action="append", default=[])
    parser.add_argument("--caveat", action="append", default=[])
    parser.add_argument("--creator", default="nAIM release pipeline")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    filter_scope = json.loads(args.filter_scope_json)
    if not isinstance(filter_scope, dict):
        raise ValueError("filter_scope_json must decode to an object")
    context = ManifestContext(
        source_snapshot_id=args.source_snapshot_id,
        data_mode=args.data_mode,
        reporting_period=args.reporting_period,
        comparison_period=args.comparison_period,
        dataset_profile=args.dataset_profile,
        dataset_hash=_value(args.dataset_hash, args.dataset_hash_reason, "dataset_hash"),
        configuration_hash=_value(
            args.configuration_hash,
            args.configuration_hash_reason,
            "configuration_hash",
        ),
        model_version=_value(args.model_version, args.model_version_reason, "model_version"),
        api_version=_value(args.api_version, args.api_version_reason, "api_version"),
        script_version=_value(args.script_version, args.script_version_reason, "script_version"),
        metric_registry_version=args.metric_registry_version,
        filter_scope=filter_scope,
        evidence_ids=tuple(args.evidence_id),
        data_quality_result=args.data_quality_result,
        synthetic_data=args.synthetic_data == "true",
        validation_status=args.validation_status,
        creator=args.creator,
        source_workspace=args.source_workspace,
        artifact_version=args.artifact_version,
        dependencies=tuple(args.dependency),
        validation_tests=tuple(args.validation_test),
        validation_evidence=tuple(args.validation_evidence),
        caveats=tuple(args.caveat),
    )
    written: list[str] = []
    for requested in args.artifacts:
        artifact = requested if requested.is_absolute() else REPOSITORY_ROOT / requested
        payload = build_manifest(artifact, context, source_inputs=args.source_input)
        target = write_manifest(payload, artifact)
        written.append(portable_path(target, REPOSITORY_ROOT))
    print(json.dumps({"status": "PASS", "manifests": written}, indent=2))


if __name__ == "__main__":
    main()
