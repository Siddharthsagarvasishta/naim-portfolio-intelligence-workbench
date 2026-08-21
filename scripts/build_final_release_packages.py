#!/usr/bin/env python3
"""Build the cycle-safe source, research, GitHub, and screenshot release ZIPs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LEDGER_NAME = "PACKAGE_CONTENTS.json"
LEDGER_SCHEMA_VERSION = "1.0.0"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
RELEASE_CORE_EVIDENCE = "outputs/nAIM_Release_Core_Evidence.json"
RETIRED_BRAND = bytes((65, 101, 103, 105, 115)).decode("ascii")
FINAL_RELEASE_EVIDENCE = "nAIM_Release_Evidence.json"

PACKAGE_TARGETS = {
    "source": "nAIM_Portfolio_Intelligence_Workbench_Source.zip",
    "research": "nAIM_Research_Package.zip",
    "github": "nAIM_GitHub_Release_Package.zip",
    "screenshots": "nAIM_Screenshots.zip",
}
PACKAGE_ROOTS = {
    "source": "naim-portfolio-intelligence-workbench",
    "research": "naim-research-package",
    "github": "naim-github-release",
    "screenshots": "naim-screenshots",
}
PACKAGE_ORDER = ("source", "research", "screenshots", "github")

SOURCE_EXCLUDED_TOP_LEVEL = {
    ".git",
    ".hypothesis",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vinext",
    ".wrangler",
    "build",
    "coverage",
    "data",
    "dist",
    "drizzle",
    "htmlcov",
    "node_modules",
    "outputs",
    "work",
}
EXCLUDED_DIRECTORY_NAMES = {
    "__pycache__",
    ".cache",
    ".mypy_cache",
    ".parcel-cache",
    ".turbo",
}
FORBIDDEN_ARCHIVE_COMPONENTS = {
    ".git",
    ".hypothesis",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vinext",
    ".wrangler",
    "__pycache__",
    "dist",
    "node_modules",
    "outputs",
    "work",
}
EXCLUDED_FILE_SUFFIXES = {
    ".coverage",
    ".duckdb",
    ".log",
    ".parquet",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
}
SOURCE_EXCLUDED_FILES = {
    ".env",
    ".DS_Store",
    "AGENT_WORK_LEDGER.md",
    "CONTINUATION_STATUS.md",
    "hyperd.log",
    "tsconfig.tsbuildinfo",
}

SOURCE_REQUIRED_PATHS = (
    ".env.example",
    "LICENSE",
    "Makefile",
    "README.md",
    "app/page.tsx",
    "build/sites-vite-plugin.ts",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "scripts/build_final_release_packages.py",
    "src/naim_risk/__init__.py",
    "tests/conftest.py",
    "vite.config.ts",
    "work/artifacts/readiness/build_readiness_matrix.mjs",
)

OFFICE_BUILDER_PATHS = (
    ".artifact-workbook/build_naim_workbook.mjs",
    ".artifact-workbook/validate_naim_presentation.mjs",
    ".artifact-workbook/linkedin-carousel/build_linkedin_carousel.mjs",
    ".artifact-workbook/linkedin-carousel/package.json",
    ".artifact-workbook/linkedin-carousel/source-notes.txt",
    ".artifact-workbook/release-deck-edit/edit_release_presentation.mjs",
    ".artifact-workbook/release-deck-edit/inspect_object.mjs",
    ".artifact-workbook/release-deck-edit/package.json",
)

RESEARCH_REQUIRED_PATHS = (
    RELEASE_CORE_EVIDENCE,
    "exports/validation/evidence_snapshot.json",
    "outputs/nAIM_Release_Readiness_Matrix.json",
    "outputs/nAIM_Release_Readiness_Matrix.xlsx",
    "outputs/validation/final_cross_artifact_reconciliation.json",
    "outputs/validation/release_readiness_workbook_validation.json",
)

FINAL_RECONCILIATION_PATH = "outputs/validation/final_cross_artifact_reconciliation.json"
FINAL_RECONCILIATION_CHANNELS = (
    "api_service_evidence",
    "ui_snapshot",
    "excel_workbook",
    "powerpoint_review",
    "tableau_hyper",
    "power_bi_validation",
    "streamlit_snapshot",
    "static_share_site",
    "linkedin_carousel",
)

RESEARCH_METHOD_DOCS = (
    "docs/advanced_statistics_methodology.md",
    "docs/analytical_methodology.md",
    "docs/artifact_provenance.md",
    "docs/cross_artifact_reconciliation.md",
    "docs/customer_membership_methodology.md",
    "docs/data_quality_framework.md",
    "docs/limitations.md",
    "docs/market_risk_methodology.md",
    "docs/metric_dictionary.md",
    "docs/model_governance.md",
    "docs/network_dependency_methodology.md",
    "docs/operations_capacity_methodology.md",
    "docs/partner_analytics_methodology.md",
    "docs/peer_analogue_methodology.md",
    "docs/performance_validation.md",
    "docs/rating_methodology.md",
    "docs/release_evidence_schema.md",
    "docs/security_and_privacy.md",
    "docs/security_test_results.md",
    "docs/statistical_template_catalogue.md",
    "docs/threat_model.md",
    "docs/vendor_oversight_methodology.md",
)

RESEARCH_OPTIONAL_VALIDATION_PATHS = (
    "exports/validation/governed_formula_metadata.csv",
    "exports/validation/interop_evidence_snapshot.json",
    "exports/validation/interop_reconciliation_totals.csv",
    "outputs/contracts/openapi_validation.json",
    "outputs/validation/npm_audit_after_summary.json",
    "outputs/validation/office_presentation_validation.json",
    "outputs/validation/office_workbook_validation.json",
    "outputs/validation/security_scan.json",
    "outputs/validation/security_test_results.json",
    "outputs/validation/test_results.json",
)

GITHUB_REQUIRED_PACKAGES = (
    "nAIM_Portfolio_Intelligence_Workbench_Source.zip",
    "nAIM_Portfolio_Intelligence_Workbench.xlsx",
    "nAIM_Portfolio_Intelligence_Review.pptx",
    "nAIM_Tableau_Desktop_Package.zip",
    "nAIM_PowerBI_Desktop_Package.zip",
    "nAIM_SAS_Compatibility_Package.zip",
    "nAIM_Research_Package.zip",
    "nAIM_LinkedIn_Showcase.zip",
    "nAIM_Screenshots.zip",
)

GITHUB_USER_DOCS = (
    "README.md",
    "LICENSE",
    "docs/api_guide.md",
    "docs/capability_status.md",
    "docs/data_onboarding_guide.md",
    "docs/instant_demo_guide.md",
    "docs/limitations.md",
    "docs/local_lifecycle_and_database_recovery.md",
    "docs/security_and_privacy.md",
    "outputs/review/CURRENT_PRODUCT_STATE.json",
    "outputs/review/USER_REVIEW_CHECKLIST.md",
    "outputs/review/USER_REVIEW_PACKET.md",
    "outputs/review/review_index.html",
)

REQUIRED_SCREENSHOT_VIEWS = (
    "start-here",
    "why-naim",
    "how-naim-works",
    "use-case-library",
    "command-centre",
    "trends",
    "vintage",
    "strategy",
    "root-cause",
    "market-risk",
    "advanced-statistics",
    "partner",
    "vendor",
    "customer-membership",
    "investigations",
    "data-quality",
    "methodology",
    "capability-status",
    "download-centre",
    "instant-demo",
)

NUMBERED_DUPLICATE = re.compile(r"^.+ [2-9][0-9]*(?:\.[^./]+)?$")
WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
PRIVATE_KEY = re.compile(
    rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
    re.IGNORECASE,
)
HIGH_CONFIDENCE_TOKENS = (
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"xox[baprs]-[A-Za-z0-9-]{20,}"),
)
SECRET_ASSIGNMENT = re.compile(
    r"^\s*[\"']?(?P<key>(?:[A-Za-z0-9]+_)*(?:API_KEY|PASSWORD|SECRET|CLIENT_SECRET)"
    r"|TOKEN|ACCESS_TOKEN|AUTH_TOKEN|BEARER_TOKEN|REFRESH_TOKEN)"
    r"[\"']?\s*[:=]\s*(?P<value>[^\s#,]+)",
    re.IGNORECASE | re.MULTILINE,
)
PLACEHOLDER_MARKERS = {
    "changeme",
    "contract-",
    "dummy",
    "example",
    "fake",
    "hidden",
    "local-only",
    "not-set",
    "placeholder",
    "replace",
    "sample",
    "test-only",
}


class PackageBuildError(RuntimeError):
    """A fail-closed package planning, build, or validation error."""


@dataclass(frozen=True)
class PackageEntry:
    """One physical or deterministic virtual file destined for an archive."""

    archive_path: str
    source_classification: str
    source_path: Path | None = None
    content: bytes | None = None
    source_sha256: str | None = None

    def read_bytes(self) -> bytes:
        if self.content is not None:
            return self.content
        if self.source_path is None:
            raise PackageBuildError(f"Entry has no source: {self.archive_path}")
        return self.source_path.read_bytes()


@dataclass(frozen=True)
class PreparedEntry:
    """An entry plus the checksum and byte size committed to the ledger."""

    entry: PackageEntry
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class PackagePlan:
    """A complete deterministic release-package plan."""

    package: str
    target: Path
    archive_root: str
    entries: tuple[PackageEntry, ...]
    dependencies: tuple[dict[str, Any], ...] = ()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_repository_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    repository = root.resolve()
    if not resolved.is_relative_to(repository):
        raise PackageBuildError(f"Source is outside the repository: {path}")
    return resolved.relative_to(repository).as_posix()


def _require_regular_file(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.exists():
        raise PackageBuildError(f"Missing prerequisite: {relative}")
    if path.is_symlink():
        raise PackageBuildError(f"Symlink prerequisite is forbidden: {relative}")
    if not path.is_file():
        raise PackageBuildError(f"Prerequisite is not a regular file: {relative}")
    _portable_repository_path(path, root)
    return path


def _entry_from_path(
    root: Path,
    relative: str,
    archive_path: str,
    classification: str,
) -> PackageEntry:
    path = _require_regular_file(root, relative)
    return PackageEntry(
        archive_path=archive_path,
        source_classification=classification,
        source_path=path,
    )


def _entry_from_bytes(
    archive_path: str,
    classification: str,
    content: bytes,
    *,
    source_sha256: str | None = None,
) -> PackageEntry:
    return PackageEntry(
        archive_path=archive_path,
        source_classification=classification,
        content=content,
        source_sha256=source_sha256,
    )


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackageBuildError(f"Invalid JSON prerequisite {label}: {error}") from error


def _validate_archive_path(name: str, *, target_name: str | None = None) -> None:
    if not name or "\\" in name or name.startswith("/") or WINDOWS_ABSOLUTE.match(name):
        raise PackageBuildError(f"Archive path is not portable: {name!r}")
    pure = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise PackageBuildError(f"Archive path is not normalised: {name!r}")
    if pure.as_posix() != name:
        raise PackageBuildError(f"Archive path is not canonical POSIX: {name!r}")
    if any(part in FORBIDDEN_ARCHIVE_COMPONENTS for part in pure.parts):
        raise PackageBuildError(f"Generated/runtime directory leaked into package: {name}")
    if any(part.endswith(".egg-info") for part in pure.parts):
        raise PackageBuildError(f"Generated package metadata leaked into package: {name}")

    basename = pure.name
    lower = basename.lower()
    if RETIRED_BRAND in name:
        raise PackageBuildError(f"Retired branded name is forbidden: {name}")
    if lower == "measures 2.dax" or NUMBERED_DUPLICATE.match(basename):
        raise PackageBuildError(f"Numbered stale duplicate is forbidden: {name}")
    if basename == FINAL_RELEASE_EVIDENCE:
        raise PackageBuildError(f"Cycle-bearing final release evidence is forbidden: {name}")
    if lower == ".env" or (lower.startswith(".env.") and lower != ".env.example"):
        raise PackageBuildError(f"Environment file is forbidden: {name}")
    if lower == "secrets.toml" or lower.endswith((".key", ".pem", ".p12", ".pfx")):
        raise PackageBuildError(f"Secret-bearing filename is forbidden: {name}")
    if target_name:
        own_manifest = f"{target_name}.manifest.json".lower()
        if lower in {target_name.lower(), own_manifest}:
            raise PackageBuildError(f"Self-referential package member is forbidden: {name}")


def _secret_assignment_value(value: str) -> str:
    return value.strip().strip("\"'").rstrip(",;")


def _validate_no_secrets(name: str, content: bytes) -> None:
    if PRIVATE_KEY.search(content) or any(pattern.search(content) for pattern in HIGH_CONFIDENCE_TOKENS):
        raise PackageBuildError(f"High-confidence secret pattern found in {name}")
    if b"\x00" in content:
        return
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return
    code_suffixes = {".js", ".mjs", ".py", ".ts", ".tsx"}
    suffix = PurePosixPath(name).suffix.lower()
    for match in SECRET_ASSIGNMENT.finditer(text):
        raw_value = match.group("value")
        if suffix in code_suffixes and not raw_value.startswith(("\"", "'")):
            continue
        value = _secret_assignment_value(raw_value)
        lowered = value.lower()
        if not value or value.startswith(("${", "<")):
            continue
        if re.fullmatch(r"[A-Z][A-Z0-9_]+", value):
            continue
        if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
            continue
        if any(character in value for character in "(){}[]"):
            continue
        if len(value) >= 8:
            raise PackageBuildError(
                f"Possible assigned secret found in {name} ({match.group('key')})"
            )


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return (mode & 0o170000) == 0o120000


def _validate_embedded_zip(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos if not item.is_dir()]
            if len(names) != len(set(names)):
                raise PackageBuildError(f"Embedded archive has duplicate paths: {path.name}")
            for info in infos:
                if info.is_dir():
                    continue
                _validate_archive_path(info.filename)
                if _is_zip_symlink(info):
                    raise PackageBuildError(
                        f"Embedded archive contains a symlink: {path.name}:{info.filename}"
                    )
                suffix = PurePosixPath(info.filename).suffix.lower()
                if suffix in {
                    ".csv",
                    ".dax",
                    ".ini",
                    ".json",
                    ".m",
                    ".md",
                    ".py",
                    ".sas",
                    ".sql",
                    ".txt",
                    ".vbs",
                    ".xml",
                    ".yaml",
                    ".yml",
                }:
                    _validate_no_secrets(f"{path.name}:{info.filename}", archive.read(info))
    except zipfile.BadZipFile as error:
        raise PackageBuildError(f"Invalid embedded ZIP/Office file: {path}") from error


def _validate_physical_entry(entry: PackageEntry) -> None:
    _validate_archive_path(entry.archive_path)
    content = entry.read_bytes()
    _validate_no_secrets(entry.archive_path, content)
    if entry.source_path and entry.source_path.suffix.lower() in {".zip", ".xlsx", ".pptx"}:
        _validate_embedded_zip(entry.source_path)


def _source_file_is_excluded(relative: PurePosixPath) -> bool:
    basename = relative.name
    lower = basename.lower()
    if basename in SOURCE_EXCLUDED_FILES:
        return True
    if basename.startswith(".coverage") or basename.endswith(".inspect.ndjson"):
        return True
    if NUMBERED_DUPLICATE.match(basename) or RETIRED_BRAND in relative.as_posix():
        return True
    if lower == "measures 2.dax":
        return True
    if lower == ".env" or (lower.startswith(".env.") and lower != ".env.example"):
        return True
    if lower.endswith(tuple(EXCLUDED_FILE_SUFFIXES)):
        return True
    parts = relative.parts
    if len(parts) >= 3 and parts[0] == "exports" and parts[2] == "data":
        return True
    if len(parts) >= 2 and parts[:2] == ("exports", "validation"):
        return True
    return False


def _source_classification(relative: PurePosixPath) -> str:
    top = relative.parts[0]
    if top == "tests":
        return "AUTHORED_TEST"
    if top == "docs" or relative.name in {"README.md", "LICENSE"}:
        return "AUTHORED_DOCUMENTATION"
    if top in {"config", "models", "schemas", ".openai", ".github"}:
        return "AUTHORED_CONFIGURATION"
    if top in {"scripts", "sql", "alembic"}:
        return "AUTHORED_BUILD_OR_MIGRATION"
    if top == "exports":
        return "AUTHORED_INTEROPERABILITY_SOURCE"
    if top in {"public", "apps"}:
        return "AUTHORED_APPLICATION_ASSET"
    return "AUTHORED_SOURCE"


def _collect_source_entries(root: Path) -> tuple[PackageEntry, ...]:
    for required in SOURCE_REQUIRED_PATHS:
        _require_regular_file(root, required)

    archive_root = PACKAGE_ROOTS["source"]
    entries: list[PackageEntry] = []
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        relative_current = current.relative_to(root)
        if relative_current == Path("."):
            directory_names[:] = sorted(
                name
                for name in directory_names
                if name not in SOURCE_EXCLUDED_TOP_LEVEL and name != ".artifact-workbook"
            )
        else:
            directory_names[:] = sorted(
                name
                for name in directory_names
                if name not in EXCLUDED_DIRECTORY_NAMES and not name.endswith(".egg-info")
            )
        for directory_name in directory_names:
            directory = current / directory_name
            if directory.is_symlink():
                raise PackageBuildError(
                    f"Symlink in selected source tree: {directory.relative_to(root).as_posix()}"
                )
        for file_name in sorted(file_names):
            path = current / file_name
            relative = PurePosixPath(path.relative_to(root).as_posix())
            if relative.as_posix() == "vite.config.ts" or _source_file_is_excluded(relative):
                continue
            if path.is_symlink():
                raise PackageBuildError(f"Symlink source is forbidden: {relative.as_posix()}")
            entries.append(
                _entry_from_path(
                    root,
                    relative.as_posix(),
                    f"{archive_root}/{relative.as_posix()}",
                    _source_classification(relative),
                )
            )

    vite_path = _require_regular_file(root, "vite.config.ts")
    vite_source = vite_path.read_bytes()
    old_import = b'"./build/sites-vite-plugin"'
    new_import = b'"./release-builders/sites-vite-plugin"'
    if old_import not in vite_source:
        raise PackageBuildError("vite.config.ts no longer has the governed Sites builder import")
    entries.append(
        _entry_from_bytes(
            f"{archive_root}/vite.config.ts",
            "AUTHORED_CONFIGURATION_PORTABLE_REWRITE",
            vite_source.replace(old_import, new_import, 1),
            source_sha256=sha256_bytes(vite_source),
        )
    )
    entries.append(
        _entry_from_path(
            root,
            "build/sites-vite-plugin.ts",
            f"{archive_root}/release-builders/sites-vite-plugin.ts",
            "AUTHORED_BUILD_TOOL_RELOCATED",
        )
    )
    entries.append(
        _entry_from_path(
            root,
            "work/artifacts/readiness/build_readiness_matrix.mjs",
            f"{archive_root}/release-builders/readiness/build_readiness_matrix.mjs",
            "AUTHORED_READINESS_BUILDER_RELOCATED",
        )
    )
    for relative in OFFICE_BUILDER_PATHS:
        path = root / relative
        if not path.exists():
            continue
        destination = relative.removeprefix(".artifact-workbook/")
        entries.append(
            _entry_from_path(
                root,
                relative,
                f"{archive_root}/release-builders/office/{destination}",
                "AUTHORED_OFFICE_BUILDER_RELOCATED",
            )
        )
    return tuple(entries)


def _portable_json_copy(path: Path, root: Path) -> bytes:
    payload = _read_json(path, _portable_repository_path(path, root))
    root_text = root.resolve().as_posix()

    def make_portable(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): make_portable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [make_portable(item) for item in value]
        if isinstance(value, str) and value.startswith(f"{root_text}/"):
            return value[len(root_text) + 1 :]
        return value

    return _json_bytes(make_portable(payload))


def _core_evidence_dependency(root: Path) -> tuple[PackageEntry, dict[str, Any]]:
    source = _require_regular_file(root, RELEASE_CORE_EVIDENCE)
    payload = _read_json(source, RELEASE_CORE_EVIDENCE)
    if not isinstance(payload, dict) or not payload:
        raise PackageBuildError("Release Core Evidence must be a non-empty JSON object")
    digest = sha256_file(source)
    dependency = {
        "path": RELEASE_CORE_EVIDENCE,
        "sha256": digest,
        "size_bytes": source.stat().st_size,
        "source_classification": "RELEASE_CORE_EVIDENCE",
    }
    return (
        PackageEntry(
            archive_path="",
            source_classification="RELEASE_CORE_EVIDENCE",
            source_path=source,
        ),
        dependency,
    )


def _assert_final_reconciliation_gate(root: Path, package_label: str) -> Path:
    path = _require_regular_file(root, FINAL_RECONCILIATION_PATH)
    payload = _read_json(path, FINAL_RECONCILIATION_PATH)
    channels = payload.get("channels")
    if not isinstance(channels, list):
        raise PackageBuildError(
            f"{package_label} package blocked: final reconciliation channels are missing"
        )
    channel_ids = [
        str(item.get("channel_id") or "") if isinstance(item, dict) else ""
        for item in channels
    ]
    if channel_ids != list(FINAL_RECONCILIATION_CHANNELS):
        raise PackageBuildError(
            f"{package_label} package blocked: final reconciliation channel contract drifted"
        )

    streamlit_incomplete = False
    for channel in channels:
        if not isinstance(channel, dict) or channel.get("required") is not True:
            raise PackageBuildError(
                f"{package_label} package blocked: final reconciliation channel is invalid"
            )
        channel_id = str(channel.get("channel_id") or "")
        status = str(channel.get("status") or "")
        checks = [item for item in channel.get("checks") or [] if isinstance(item, dict)]
        required_checks = [item for item in checks if item.get("required") is True]
        if not required_checks:
            raise PackageBuildError(
                f"{package_label} package blocked: {channel_id} has no required checks"
            )
        if channel_id == "streamlit_snapshot" and status == "INCOMPLETE":
            streamlit_incomplete = True
            outcomes = {str(item.get("outcome") or "") for item in required_checks}
            if not outcomes.intersection({"MISSING", "UNVERIFIABLE"}) or outcomes.difference(
                {"PASS", "MISSING", "UNVERIFIABLE"}
            ):
                raise PackageBuildError(
                    f"{package_label} package blocked: Streamlit boundary is not explicit"
                )
        elif status != "PASS" or any(
            str(item.get("outcome") or "") != "PASS" for item in required_checks
        ):
            raise PackageBuildError(
                f"{package_label} package blocked: required final channel {channel_id} is not PASS"
            )

        artifact_paths = channel.get("artifact_paths")
        artifacts = channel.get("artifacts")
        if not isinstance(artifact_paths, list) or not isinstance(artifacts, list):
            raise PackageBuildError(
                f"{package_label} package blocked: {channel_id} artifact ledger is missing"
            )
        if status == "PASS" and (not artifact_paths or not artifacts):
            raise PackageBuildError(
                f"{package_label} package blocked: {channel_id} has no artifact evidence"
            )
        recorded_paths: list[str] = []
        for record in artifacts:
            if not isinstance(record, dict):
                raise PackageBuildError(
                    f"{package_label} package blocked: {channel_id} artifact record is invalid"
                )
            relative = str(record.get("path") or "")
            artifact = _require_regular_file(root, relative)
            recorded_paths.append(relative)
            if record.get("bytes") != artifact.stat().st_size or record.get(
                "sha256"
            ) != sha256_file(artifact):
                raise PackageBuildError(
                    f"{package_label} package blocked: {channel_id} artifact ledger is stale"
                )
        if sorted(str(value) for value in artifact_paths) != sorted(recorded_paths):
            raise PackageBuildError(
                f"{package_label} package blocked: {channel_id} artifact paths disagree"
            )

    expected_result = "INCOMPLETE" if streamlit_incomplete else "PASS"
    expected_release_allowed = expected_result == "PASS"
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if (
        payload.get("result") != expected_result
        or payload.get("release_allowed") is not expected_release_allowed
        or summary.get("failed_check_count") != 0
        or summary.get("failed_channels") not in ([], None)
    ):
        raise PackageBuildError(
            f"{package_label} package blocked: final reconciliation result is inconsistent"
        )
    return path


def _assert_research_gates(root: Path) -> None:
    readiness = _read_json(
        _require_regular_file(root, "outputs/nAIM_Release_Readiness_Matrix.json"),
        "outputs/nAIM_Release_Readiness_Matrix.json",
    )
    if readiness.get("release_allowed") is not True:
        raise PackageBuildError("Research package blocked: readiness release_allowed is not true")
    _assert_final_reconciliation_gate(root, "Research")
    workbook_validation = _read_json(
        _require_regular_file(
            root, "outputs/validation/release_readiness_workbook_validation.json"
        ),
        "outputs/validation/release_readiness_workbook_validation.json",
    )
    status = str(
        workbook_validation.get("status")
        or workbook_validation.get("result")
        or workbook_validation.get("validation_status")
        or ""
    ).upper()
    if status not in {"PASS", "VALID", "VALIDATED"}:
        raise PackageBuildError("Research package blocked: readiness workbook validation is not PASS")


def _collect_research_entries(
    root: Path,
) -> tuple[tuple[PackageEntry, ...], tuple[dict[str, Any], ...]]:
    for required in RESEARCH_REQUIRED_PATHS:
        _require_regular_file(root, required)
    for required in RESEARCH_METHOD_DOCS:
        _require_regular_file(root, required)
    _assert_research_gates(root)

    archive_root = PACKAGE_ROOTS["research"]
    core_entry, dependency = _core_evidence_dependency(root)
    entries: list[PackageEntry] = [
        PackageEntry(
            archive_path=f"{archive_root}/evidence/nAIM_Release_Core_Evidence.json",
            source_classification=core_entry.source_classification,
            source_path=core_entry.source_path,
        ),
        _entry_from_path(
            root,
            "exports/validation/evidence_snapshot.json",
            f"{archive_root}/evidence/canonical_evidence_snapshot.json",
            "CANONICAL_EVIDENCE",
        ),
        _entry_from_path(
            root,
            FINAL_RECONCILIATION_PATH,
            f"{archive_root}/evidence/cross_artifact_reconciliation.json",
            "CROSS_TOOL_VALIDATION",
        ),
        _entry_from_path(
            root,
            "outputs/nAIM_Release_Readiness_Matrix.json",
            f"{archive_root}/readiness/nAIM_Release_Readiness_Matrix.json",
            "RELEASE_READINESS",
        ),
        _entry_from_path(
            root,
            "outputs/nAIM_Release_Readiness_Matrix.xlsx",
            f"{archive_root}/readiness/nAIM_Release_Readiness_Matrix.xlsx",
            "RELEASE_READINESS",
        ),
        _entry_from_path(
            root,
            "outputs/validation/release_readiness_workbook_validation.json",
            f"{archive_root}/readiness/workbook_validation.json",
            "RELEASE_READINESS_VALIDATION",
        ),
    ]

    latest_path = root / "data/manifests/latest.json"
    if latest_path.exists():
        latest = _read_json(latest_path, "data/manifests/latest.json")
        run_id = str(latest.get("run_id", ""))
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
            raise PackageBuildError("The latest run manifest has an unsafe or missing run_id")
        run_relative = f"data/manifests/{run_id}/run_manifest.json"
        run_path = _require_regular_file(root, run_relative)
        entries.extend(
            (
                _entry_from_bytes(
                    f"{archive_root}/evidence/core_snapshot_pointer.json",
                    "IMMUTABLE_CORE_EVIDENCE_PORTABLE_COPY",
                    _portable_json_copy(latest_path, root),
                    source_sha256=sha256_file(latest_path),
                ),
                _entry_from_bytes(
                    f"{archive_root}/evidence/core_run_manifest.json",
                    "IMMUTABLE_CORE_EVIDENCE_PORTABLE_COPY",
                    _portable_json_copy(run_path, root),
                    source_sha256=sha256_file(run_path),
                ),
            )
        )

    for relative in RESEARCH_METHOD_DOCS:
        entries.append(
            _entry_from_path(
                root,
                relative,
                f"{archive_root}/methodology/{Path(relative).name}",
                "METHODOLOGY_DOCUMENTATION",
            )
        )
    for relative in RESEARCH_OPTIONAL_VALIDATION_PATHS:
        if not (root / relative).is_file():
            continue
        entries.append(
            _entry_from_path(
                root,
                relative,
                f"{archive_root}/validation/{Path(relative).name}",
                "VALIDATION_EVIDENCE",
            )
        )
    performance_root = root / "outputs/performance"
    if performance_root.is_dir():
        for path in sorted(performance_root.glob("*.json")):
            relative = path.relative_to(root).as_posix()
            entries.append(
                _entry_from_path(
                    root,
                    relative,
                    f"{archive_root}/performance/{path.name}",
                    "PERFORMANCE_EVIDENCE",
                )
            )
    return tuple(entries), (dependency,)


def _normalise_viewport(record: dict[str, Any]) -> tuple[str, int | None, int | None]:
    viewport = record.get("viewport")
    if isinstance(viewport, str):
        return viewport.lower().strip(), None, None
    if not isinstance(viewport, dict):
        raise PackageBuildError("Each screenshot capture requires a viewport")
    name = str(viewport.get("name") or viewport.get("type") or "").lower().strip()
    width = viewport.get("width")
    height = viewport.get("height")
    if width is not None and (not isinstance(width, int) or width <= 0):
        raise PackageBuildError("Screenshot viewport width must be a positive integer")
    if height is not None and (not isinstance(height, int) or height <= 0):
        raise PackageBuildError("Screenshot viewport height must be a positive integer")
    return name, width, height


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise PackageBuildError(f"Screenshot is not a valid PNG header: {path.name}")
    width, height = struct.unpack(">II", header[16:24])
    if width < 320 or height < 200:
        raise PackageBuildError(f"Screenshot dimensions are implausibly small: {path.name}")
    return width, height


def _validate_capture_index(root: Path) -> tuple[dict[str, Any], list[tuple[Path, dict[str, Any]]]]:
    index_relative = "outputs/screenshots/browser_capture_index.json"
    index_path = _require_regular_file(root, index_relative)
    index = _read_json(index_path, index_relative)
    if not isinstance(index, dict):
        raise PackageBuildError("Browser capture index must be a JSON object")
    if index.get("capture_kind") != "REAL_BROWSER" or index.get("real_browser") is not True:
        raise PackageBuildError("Screenshot package requires a REAL_BROWSER capture index")
    if str(index.get("validation_status", "")).upper() != "PASS":
        raise PackageBuildError("Screenshot capture index validation_status must be PASS")
    browser = str(index.get("browser") or index.get("capture_tool") or "")
    if "browser" not in browser.lower():
        raise PackageBuildError("Screenshot capture index must identify the browser capture tool")
    captures = index.get("captures")
    if not isinstance(captures, list) or not captures:
        raise PackageBuildError("Screenshot capture index has no captures")

    screenshots_root = root / "outputs/screenshots"
    selected: list[tuple[Path, dict[str, Any]]] = []
    declared_files: set[str] = set()
    desktop_views: set[str] = set()
    device_viewports: set[str] = set()
    for raw_record in captures:
        if not isinstance(raw_record, dict):
            raise PackageBuildError("Screenshot capture records must be JSON objects")
        record = dict(raw_record)
        view_id = str(record.get("view_id", "")).strip().lower()
        file_name = str(record.get("file", "")).strip()
        if not view_id or not file_name:
            raise PackageBuildError("Each screenshot capture requires view_id and file")
        _validate_archive_path(file_name)
        if PurePosixPath(file_name).suffix.lower() != ".png":
            raise PackageBuildError(f"Screenshot capture is not PNG: {file_name}")
        if file_name in declared_files:
            raise PackageBuildError(f"Screenshot capture file is declared twice: {file_name}")
        if record.get("real_browser") is not True:
            raise PackageBuildError(f"Screenshot capture is not marked real_browser: {file_name}")
        if str(record.get("validation_status", "")).upper() != "PASS":
            raise PackageBuildError(f"Screenshot capture is not validated: {file_name}")
        availability = str(record.get("availability_state", "LIVE")).upper()
        if availability in {"UNAVAILABLE", "ERROR", "STALE"}:
            raise PackageBuildError(f"Screenshot represents an invalid state: {file_name}")

        viewport_name, expected_width, expected_height = _normalise_viewport(record)
        if viewport_name == "desktop":
            desktop_views.add(view_id)
        if viewport_name in {"tablet", "mobile"}:
            device_viewports.add(viewport_name)
        path = (screenshots_root / file_name).resolve()
        if not path.is_relative_to(screenshots_root.resolve()):
            raise PackageBuildError(f"Screenshot escapes its governed directory: {file_name}")
        if path.is_symlink() or not path.is_file():
            raise PackageBuildError(f"Screenshot file is missing or a symlink: {file_name}")
        width, height = _png_dimensions(path)
        if expected_width is not None and width < expected_width:
            raise PackageBuildError(f"Screenshot is narrower than its viewport: {file_name}")
        if expected_height is not None and height < expected_height:
            raise PackageBuildError(f"Screenshot is shorter than its viewport: {file_name}")
        declared_files.add(file_name)
        selected.append((path, record))

    missing_views = sorted(set(REQUIRED_SCREENSHOT_VIEWS) - desktop_views)
    if missing_views:
        raise PackageBuildError(
            "Screenshot package lacks required desktop views: " + ", ".join(missing_views)
        )
    missing_device_viewports = {"tablet", "mobile"} - device_viewports
    if missing_device_viewports:
        raise PackageBuildError(
            "Screenshot package lacks selected device captures: "
            + ", ".join(sorted(missing_device_viewports))
        )
    on_disk = {
        path.relative_to(screenshots_root).as_posix()
        for path in screenshots_root.rglob("*.png")
        if path.is_file()
    }
    undeclared = sorted(on_disk - declared_files)
    if undeclared:
        raise PackageBuildError(
            "Screenshot directory contains undeclared or stale PNGs: " + ", ".join(undeclared)
        )
    return index, selected


def _collect_screenshot_entries(
    root: Path,
) -> tuple[tuple[PackageEntry, ...], tuple[dict[str, Any], ...]]:
    index, captures = _validate_capture_index(root)
    del index
    archive_root = PACKAGE_ROOTS["screenshots"]
    core_entry, dependency = _core_evidence_dependency(root)
    entries = [
        _entry_from_path(
            root,
            "outputs/screenshots/browser_capture_index.json",
            f"{archive_root}/browser_capture_index.json",
            "REAL_BROWSER_CAPTURE_INDEX",
        ),
        PackageEntry(
            archive_path=f"{archive_root}/evidence/nAIM_Release_Core_Evidence.json",
            source_classification=core_entry.source_classification,
            source_path=core_entry.source_path,
        ),
    ]
    screenshots_root = root / "outputs/screenshots"
    for path, _record in captures:
        relative = path.relative_to(screenshots_root).as_posix()
        entries.append(
            PackageEntry(
                archive_path=f"{archive_root}/captures/{relative}",
                source_classification="REAL_BROWSER_SCREENSHOT",
                source_path=path,
            )
        )
    return tuple(entries), (dependency,)


def _validate_governed_child_package(path: Path, require_ledger: bool) -> None:
    _validate_embedded_zip(path)
    if require_ledger:
        validate_package_archive(path)


def _collect_github_entries(
    root: Path,
) -> tuple[tuple[PackageEntry, ...], tuple[dict[str, Any], ...]]:
    archive_root = PACKAGE_ROOTS["github"]
    readiness_json = _require_regular_file(root, "outputs/nAIM_Release_Readiness_Matrix.json")
    readiness = _read_json(readiness_json, "outputs/nAIM_Release_Readiness_Matrix.json")
    if readiness.get("release_allowed") is not True:
        raise PackageBuildError("GitHub release package blocked: release readiness is not true")
    _assert_final_reconciliation_gate(root, "GitHub release")

    core_entry, dependency = _core_evidence_dependency(root)
    entries: list[PackageEntry] = [
        PackageEntry(
            archive_path=f"{archive_root}/evidence/nAIM_Release_Core_Evidence.json",
            source_classification=core_entry.source_classification,
            source_path=core_entry.source_path,
        ),
        _entry_from_path(
            root,
            "exports/validation/evidence_snapshot.json",
            f"{archive_root}/evidence/canonical_evidence_snapshot.json",
            "CANONICAL_EVIDENCE",
        ),
        _entry_from_path(
            root,
            FINAL_RECONCILIATION_PATH,
            f"{archive_root}/evidence/cross_artifact_reconciliation.json",
            "CROSS_TOOL_VALIDATION",
        ),
        _entry_from_path(
            root,
            "outputs/nAIM_Release_Readiness_Matrix.json",
            f"{archive_root}/readiness/nAIM_Release_Readiness_Matrix.json",
            "RELEASE_READINESS",
        ),
        _entry_from_path(
            root,
            "outputs/nAIM_Release_Readiness_Matrix.xlsx",
            f"{archive_root}/readiness/nAIM_Release_Readiness_Matrix.xlsx",
            "RELEASE_READINESS",
        ),
    ]

    for package_name in GITHUB_REQUIRED_PACKAGES:
        relative = f"outputs/{package_name}"
        path = _require_regular_file(root, relative)
        require_ledger = package_name in {
            PACKAGE_TARGETS["source"],
            PACKAGE_TARGETS["research"],
            PACKAGE_TARGETS["screenshots"],
        }
        if path.suffix.lower() == ".zip":
            _validate_governed_child_package(path, require_ledger=require_ledger)
        entries.append(
            _entry_from_path(
                root,
                relative,
                f"{archive_root}/packages/{package_name}",
                "CYCLE_SAFE_PRODUCT_PACKAGE",
            )
        )
    for relative in GITHUB_USER_DOCS:
        entries.append(
            _entry_from_path(
                root,
                relative,
                f"{archive_root}/documentation/{Path(relative).name}",
                "USER_DOCUMENTATION",
            )
        )
    return tuple(entries), (dependency,)


def create_package_plan(package: str, root: Path = REPOSITORY_ROOT) -> PackagePlan:
    if package not in PACKAGE_TARGETS:
        raise PackageBuildError(f"Unknown package: {package}")
    root = root.resolve()
    target = root / "outputs" / PACKAGE_TARGETS[package]
    dependencies: tuple[dict[str, Any], ...] = ()
    if package == "source":
        entries = _collect_source_entries(root)
    elif package == "research":
        entries, dependencies = _collect_research_entries(root)
    elif package == "screenshots":
        entries, dependencies = _collect_screenshot_entries(root)
    else:
        entries, dependencies = _collect_github_entries(root)
    return PackagePlan(
        package=package,
        target=target,
        archive_root=PACKAGE_ROOTS[package],
        entries=tuple(entries),
        dependencies=dependencies,
    )


def _prepare_plan(plan: PackagePlan) -> tuple[PreparedEntry, ...]:
    seen: set[str] = set()
    prepared: list[PreparedEntry] = []
    for entry in sorted(plan.entries, key=lambda item: item.archive_path):
        _validate_archive_path(entry.archive_path, target_name=plan.target.name)
        if entry.archive_path in seen:
            raise PackageBuildError(f"Duplicate planned archive path: {entry.archive_path}")
        seen.add(entry.archive_path)
        _validate_physical_entry(entry)
        content = entry.read_bytes()
        prepared.append(
            PreparedEntry(entry=entry, sha256=sha256_bytes(content), size_bytes=len(content))
        )
    if not prepared:
        raise PackageBuildError(f"Package has no governed content: {plan.package}")
    return tuple(prepared)


def _ledger_bytes(plan: PackagePlan, prepared: tuple[PreparedEntry, ...]) -> bytes:
    files: list[dict[str, Any]] = []
    for item in prepared:
        record: dict[str, Any] = {
            "archive_path": item.entry.archive_path,
            "sha256": item.sha256,
            "size_bytes": item.size_bytes,
            "source_classification": item.entry.source_classification,
        }
        if item.entry.source_sha256:
            record["source_sha256"] = item.entry.source_sha256
            record["transformed_for_portability"] = True
        files.append(record)
    payload = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "package": plan.package,
        "target_filename": plan.target.name,
        "archive_root": plan.archive_root,
        "deterministic_zip_timestamp": "1980-01-01T00:00:00Z",
        "cycle_exclusions": [
            FINAL_RELEASE_EVIDENCE,
            f"{plan.target.name}.manifest.json",
            plan.target.name,
            LEDGER_NAME,
        ],
        "dependencies": list(plan.dependencies),
        "files": files,
    }
    return _json_bytes(payload)


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    return info


def _write_entry(archive: zipfile.ZipFile, entry: PackageEntry) -> None:
    info = _zip_info(entry.archive_path)
    if entry.content is not None:
        archive.writestr(info, entry.content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        return
    if entry.source_path is None:
        raise PackageBuildError(f"Entry has no physical source: {entry.archive_path}")
    with entry.source_path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)


def build_package(plan: PackagePlan, *, dry_run: bool = False) -> dict[str, Any]:
    prepared = _prepare_plan(plan)
    ledger_path = f"{plan.archive_root}/{LEDGER_NAME}"
    _validate_archive_path(ledger_path, target_name=plan.target.name)
    ledger = _ledger_bytes(plan, prepared)
    summary = {
        "package": plan.package,
        "target": plan.target.relative_to(plan.target.parents[1]).as_posix(),
        "dry_run": dry_run,
        "file_count": len(prepared),
        "payload_bytes": sum(item.size_bytes for item in prepared),
        "core_evidence_sha256": next(
            (
                item["sha256"]
                for item in plan.dependencies
                if item.get("path") == RELEASE_CORE_EVIDENCE
            ),
            None,
        ),
    }
    if dry_run:
        return summary

    plan.target.parent.mkdir(parents=True, exist_ok=True)
    temporary = plan.target.with_name(f".{plan.target.name}.building")
    if temporary.exists():
        temporary.unlink()
    try:
        all_entries = [item.entry for item in prepared]
        all_entries.append(
            _entry_from_bytes(ledger_path, "PACKAGE_CONTENT_LEDGER", ledger)
        )
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            strict_timestamps=True,
        ) as archive:
            for entry in sorted(all_entries, key=lambda item: item.archive_path):
                _write_entry(archive, entry)
        validate_package_archive(temporary, expected_target_name=plan.target.name)
        os.replace(temporary, plan.target)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    summary["sha256"] = sha256_file(plan.target)
    summary["size_bytes"] = plan.target.stat().st_size
    return summary


def validate_package_archive(
    path: Path,
    *,
    expected_target_name: str | None = None,
) -> dict[str, Any]:
    target_name = expected_target_name or path.name
    try:
        with zipfile.ZipFile(path) as archive:
            infos = [item for item in archive.infolist() if not item.is_dir()]
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise PackageBuildError(f"Package contains duplicate archive paths: {path}")
            if names != sorted(names):
                raise PackageBuildError(f"Package paths are not sorted: {path}")
            for info in infos:
                _validate_archive_path(info.filename, target_name=target_name)
                if _is_zip_symlink(info):
                    raise PackageBuildError(f"Package contains a symlink: {info.filename}")
                if info.date_time != FIXED_ZIP_TIME:
                    raise PackageBuildError(f"Package has non-deterministic metadata: {info.filename}")

            ledger_names = [name for name in names if PurePosixPath(name).name == LEDGER_NAME]
            if len(ledger_names) != 1:
                raise PackageBuildError("Package must contain exactly one internal content ledger")
            ledger_name = ledger_names[0]
            try:
                ledger = json.loads(archive.read(ledger_name).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise PackageBuildError("Package content ledger is invalid JSON") from error
            if ledger.get("schema_version") != LEDGER_SCHEMA_VERSION:
                raise PackageBuildError("Package content ledger schema version is unsupported")
            records = ledger.get("files")
            if not isinstance(records, list):
                raise PackageBuildError("Package content ledger has no files array")
            declared: dict[str, dict[str, Any]] = {}
            for record in records:
                if not isinstance(record, dict):
                    raise PackageBuildError("Package content ledger has a non-object record")
                member = str(record.get("archive_path", ""))
                if member in declared:
                    raise PackageBuildError(f"Package content ledger declares {member} twice")
                if not record.get("source_classification"):
                    raise PackageBuildError(f"Package content ledger lacks classification: {member}")
                declared[member] = record
            actual = set(names) - {ledger_name}
            if set(declared) != actual:
                missing = sorted(actual - set(declared))
                undeclared = sorted(set(declared) - actual)
                raise PackageBuildError(
                    f"Ledger/archive mismatch; undeclared={missing}, missing={undeclared}"
                )
            for member, record in declared.items():
                content = archive.read(member)
                if record.get("sha256") != sha256_bytes(content):
                    raise PackageBuildError(f"Package content checksum mismatch: {member}")
                if record.get("size_bytes") != len(content):
                    raise PackageBuildError(f"Package content size mismatch: {member}")
                _validate_no_secrets(member, content)

            dependencies = ledger.get("dependencies", [])
            if not isinstance(dependencies, list):
                raise PackageBuildError("Package content ledger dependencies must be a list")
            if ledger.get("package") in {"research", "github", "screenshots"}:
                core_dependencies = [
                    item
                    for item in dependencies
                    if isinstance(item, dict) and item.get("path") == RELEASE_CORE_EVIDENCE
                ]
                if len(core_dependencies) != 1 or not re.fullmatch(
                    r"[0-9a-f]{64}", str(core_dependencies[0].get("sha256", ""))
                ):
                    raise PackageBuildError(
                        "Post-decision package ledger lacks the Release Core Evidence SHA-256"
                    )
                core_records = [
                    record
                    for record in records
                    if isinstance(record, dict)
                    and record.get("source_classification") == "RELEASE_CORE_EVIDENCE"
                ]
                if len(core_records) != 1 or any(
                    core_dependencies[0].get(field) != core_records[0].get(field)
                    for field in ("sha256", "size_bytes")
                ):
                    raise PackageBuildError(
                        "Release Core Evidence dependency does not match the packaged evidence"
                    )
            return {
                "path": path.as_posix(),
                "package": ledger.get("package"),
                "file_count": len(actual),
                "sha256": sha256_file(path),
            }
    except zipfile.BadZipFile as error:
        raise PackageBuildError(f"Package is not a valid ZIP: {path}") from error


def build_selected_packages(
    packages: Iterable[str],
    *,
    root: Path = REPOSITORY_ROOT,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    selected = list(dict.fromkeys(packages))
    if not selected:
        raise PackageBuildError("At least one --package value is required")
    unknown = sorted(set(selected) - set(PACKAGE_TARGETS))
    if unknown:
        raise PackageBuildError("Unknown packages: " + ", ".join(unknown))
    ordered = [package for package in PACKAGE_ORDER if package in selected]
    results: list[dict[str, Any]] = []
    for package in ordered:
        plan = create_package_plan(package, root=root)
        results.append(build_package(plan, dry_run=dry_run))
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package",
        action="append",
        choices=sorted(PACKAGE_TARGETS),
        required=True,
        help="Package to validate/build; repeat for a topologically ordered release build.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate all prerequisites and content without writing output bytes.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        results = build_selected_packages(args.package, dry_run=args.dry_run)
    except (OSError, PackageBuildError, ValueError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"status": "PASS", "packages": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
