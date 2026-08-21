#!/usr/bin/env python3
"""Validate the nAIM capability truth registry and its human-readable mirror."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = REPOSITORY_ROOT / "config" / "feature_status.yaml"
DEFAULT_DOCUMENTATION = REPOSITORY_ROOT / "docs" / "capability_status.md"

ALLOWED_STATUSES = (
    "LIVE",
    "INTEGRATION_ONLY",
    "DOCUMENTED",
    "DISABLED",
    "NOT_IMPLEMENTED",
)
REQUIRED_TOP_LEVEL_FIELDS = {
    "schema_version",
    "registry_version",
    "product",
    "description",
    "allowed_statuses",
    "status_definitions",
    "features",
}
REQUIRED_FEATURE_FIELDS = {
    "feature_id",
    "name",
    "status",
    "backend_endpoint",
    "frontend_route",
    "calculation_module",
    "test_evidence",
    "artifact_evidence",
    "limitation",
    "last_validation_date",
    "owner",
    "version",
}
LIST_FIELDS = (
    "backend_endpoint",
    "frontend_route",
    "calculation_module",
    "test_evidence",
    "artifact_evidence",
)
EVIDENCE_PATH_FIELDS = (
    "calculation_module",
    "test_evidence",
    "artifact_evidence",
)
FEATURE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
DOCUMENT_ROW_PATTERN = re.compile(
    r"^\|\s*`(?P<feature_id>[A-Z][A-Z0-9_]*)`\s*"
    r"\|\s*`(?P<status>[A-Z_]+)`\s*"
    r"\|\s*(?P<name>[^|]+?)\s*\|"
)


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    """Load JSON-compatible YAML without requiring a YAML dependency."""

    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Capability registry root must be an object")
    return payload


def _string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_date(value: object, field: str, errors: list[str]) -> None:
    if not _string(value):
        errors.append(f"{field} must be an ISO date string")
        return
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        errors.append(f"{field} must use YYYY-MM-DD")
        return
    if parsed > date.today():
        errors.append(f"{field} cannot be in the future")


def _validate_list_field(
    feature_id: str,
    field: str,
    value: object,
    errors: list[str],
) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{feature_id}.{field} must be a list")
        return []
    if any(not _string(item) for item in value):
        errors.append(f"{feature_id}.{field} entries must be non-empty strings")
        return []
    if len(value) != len(set(value)):
        errors.append(f"{feature_id}.{field} must not contain duplicates")
    return [str(item) for item in value]


def _validate_evidence_path(
    feature_id: str,
    field: str,
    value: str,
    repository_root: Path,
    errors: list[str],
) -> None:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        errors.append(f"{feature_id}.{field} must use a safe repository-relative path: {value}")
        return
    resolved = repository_root / relative
    if not resolved.exists():
        errors.append(f"{feature_id}.{field} evidence path does not exist: {value}")


def validate_registry(
    registry: Mapping[str, Any],
    repository_root: Path = REPOSITORY_ROOT,
) -> list[str]:
    """Return every schema, evidence, and status-claim error."""

    errors: list[str] = []
    missing_top = sorted(REQUIRED_TOP_LEVEL_FIELDS - set(registry))
    if missing_top:
        errors.append(f"Registry is missing top-level fields: {', '.join(missing_top)}")

    allowed = registry.get("allowed_statuses")
    if allowed != list(ALLOWED_STATUSES):
        errors.append("allowed_statuses must exactly match the governed status vocabulary")

    definitions = registry.get("status_definitions")
    if not isinstance(definitions, Mapping) or set(definitions) != set(ALLOWED_STATUSES):
        errors.append("status_definitions must define every and only allowed status")
    elif any(not _string(definitions[status]) for status in ALLOWED_STATUSES):
        errors.append("Every status definition must be a non-empty string")

    product = registry.get("product")
    if product != "nAIM Portfolio Intelligence Workbench":
        errors.append("product must use the canonical nAIM identity")

    features = registry.get("features")
    if not isinstance(features, list) or not features:
        errors.append("features must be a non-empty list")
        return errors

    seen_ids: set[str] = set()
    for index, feature in enumerate(features):
        location = f"features[{index}]"
        if not isinstance(feature, Mapping):
            errors.append(f"{location} must be an object")
            continue
        missing = sorted(REQUIRED_FEATURE_FIELDS - set(feature))
        if missing:
            errors.append(f"{location} is missing fields: {', '.join(missing)}")

        feature_id_value = feature.get("feature_id")
        feature_id = str(feature_id_value) if feature_id_value is not None else location
        if not _string(feature_id_value) or not FEATURE_ID_PATTERN.fullmatch(feature_id):
            errors.append(f"{location}.feature_id must use uppercase snake case")
        elif feature_id in seen_ids:
            errors.append(f"Duplicate feature_id: {feature_id}")
        seen_ids.add(feature_id)

        for field in ("name", "limitation", "owner"):
            if not _string(feature.get(field)):
                errors.append(f"{feature_id}.{field} must be a non-empty string")
        version = feature.get("version")
        if not _string(version) or not SEMVER_PATTERN.fullmatch(str(version)):
            errors.append(f"{feature_id}.version must use semantic version x.y.z")
        _validate_date(
            feature.get("last_validation_date"),
            f"{feature_id}.last_validation_date",
            errors,
        )

        status = feature.get("status")
        if status not in ALLOWED_STATUSES:
            errors.append(f"{feature_id}.status is not allowed: {status!r}")

        lists = {
            field: _validate_list_field(feature_id, field, feature.get(field), errors)
            for field in LIST_FIELDS
        }
        for endpoint in lists["backend_endpoint"]:
            if not endpoint.startswith("/api/"):
                errors.append(f"{feature_id}.backend_endpoint is not versioned: {endpoint}")
        for route in lists["frontend_route"]:
            if not route.startswith("/"):
                errors.append(f"{feature_id}.frontend_route must start with '/': {route}")
        for field in EVIDENCE_PATH_FIELDS:
            for evidence_path in lists[field]:
                _validate_evidence_path(
                    feature_id,
                    field,
                    evidence_path,
                    repository_root,
                    errors,
                )

        executable_claim = bool(
            lists["backend_endpoint"] or lists["frontend_route"] or lists["calculation_module"]
        )
        if status == "LIVE":
            if not executable_claim:
                errors.append(f"{feature_id} is LIVE but has no executable surface")
            if not lists["test_evidence"]:
                errors.append(f"{feature_id} is LIVE but has no focused test evidence")
            if any(not path.startswith("tests/") for path in lists["test_evidence"]):
                errors.append(f"{feature_id} LIVE test evidence must be under tests/")
        elif status == "INTEGRATION_ONLY":
            if not executable_claim and not lists["artifact_evidence"]:
                errors.append(f"{feature_id} is INTEGRATION_ONLY but has no interface or asset")
        elif status == "DOCUMENTED":
            if executable_claim or lists["test_evidence"]:
                errors.append(f"{feature_id} is DOCUMENTED but makes an executable or tested claim")
            if not lists["artifact_evidence"]:
                errors.append(f"{feature_id} is DOCUMENTED but has no documentation evidence")
        elif status == "DISABLED":
            if not lists["calculation_module"]:
                errors.append(f"{feature_id} is DISABLED but has no executable module")
        elif status == "NOT_IMPLEMENTED":
            claimed = [field for field in LIST_FIELDS if lists[field]]
            if claimed:
                errors.append(
                    f"{feature_id} is NOT_IMPLEMENTED but claims evidence in: {', '.join(claimed)}"
                )

    serialized = json.dumps(registry, sort_keys=True).casefold()
    retired_token = "a" + "egis"
    if retired_token in serialized:
        errors.append("Registry contains a retired public identity token")
    return errors


def validate_document_sync(
    registry: Mapping[str, Any],
    documentation_text: str,
) -> list[str]:
    """Check that the Markdown table mirrors every registry feature and status."""

    errors: list[str] = []
    version = registry.get("registry_version")
    if f"Registry version: `{version}`" not in documentation_text:
        errors.append("Capability documentation does not declare the registry version")

    documented: dict[str, tuple[str, str]] = {}
    duplicate_ids: set[str] = set()
    for line in documentation_text.splitlines():
        match = DOCUMENT_ROW_PATTERN.match(line)
        if not match:
            continue
        feature_id = match.group("feature_id")
        if feature_id in documented:
            duplicate_ids.add(feature_id)
        documented[feature_id] = (
            match.group("status"),
            match.group("name").strip(),
        )
    if duplicate_ids:
        errors.append(
            "Capability documentation repeats feature IDs: " + ", ".join(sorted(duplicate_ids))
        )

    expected = {
        str(feature["feature_id"]): (str(feature["status"]), str(feature["name"]))
        for feature in registry.get("features", [])
        if isinstance(feature, Mapping)
        and "feature_id" in feature
        and "status" in feature
        and "name" in feature
    }
    missing = sorted(set(expected) - set(documented))
    unknown = sorted(set(documented) - set(expected))
    if missing:
        errors.append("Capability documentation omits feature IDs: " + ", ".join(missing))
    if unknown:
        errors.append("Capability documentation has unknown feature IDs: " + ", ".join(unknown))
    for feature_id in sorted(set(expected) & set(documented)):
        if expected[feature_id] != documented[feature_id]:
            errors.append(
                f"Capability documentation is out of sync for {feature_id}: "
                f"expected {expected[feature_id]!r}, found {documented[feature_id]!r}"
            )
    return errors


def status_counts(registry: Mapping[str, Any]) -> dict[str, int]:
    """Return stable counts in governed status order."""

    counts = Counter(
        feature.get("status")
        for feature in registry.get("features", [])
        if isinstance(feature, Mapping)
    )
    return {status: int(counts.get(status, 0)) for status in ALLOWED_STATUSES}


def build_result(
    registry_path: Path,
    documentation_path: Path,
    errors: Sequence[str],
    registry: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build the stable CLI result payload."""

    return {
        "valid": not errors,
        "registry": str(registry_path),
        "documentation": str(documentation_path),
        "feature_count": len(registry.get("features", [])) if registry else 0,
        "status_counts": status_counts(registry) if registry else {},
        "errors": list(errors),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--documentation", type=Path, default=DEFAULT_DOCUMENTATION)
    args = parser.parse_args()

    errors: list[str] = []
    registry: dict[str, Any] | None = None
    try:
        registry = load_registry(args.registry)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"Unable to load registry: {exc}")
    if registry is not None:
        errors.extend(validate_registry(registry, REPOSITORY_ROOT))
        try:
            documentation_text = args.documentation.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"Unable to load capability documentation: {exc}")
        else:
            errors.extend(validate_document_sync(registry, documentation_text))

    result = build_result(args.registry, args.documentation, errors, registry)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
