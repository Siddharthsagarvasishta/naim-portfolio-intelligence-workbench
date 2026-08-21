#!/usr/bin/env python3
"""Generate and validate the deterministic nAIM OpenAPI contract."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from naim_risk.api import app

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPOSITORY_ROOT / "outputs" / "contracts" / "openapi.json"
DEFAULT_EVIDENCE = REPOSITORY_ROOT / "outputs" / "contracts" / "openapi_validation.json"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}

STRICT_CONTRACT_SCHEMAS: dict[str, dict[str, Any]] = {
    "DataMode": {
        "type": "string",
        "enum": ["LIVE", "DEMO", "OFFLINE_SNAPSHOT", "UNAVAILABLE"],
        "description": "The mutually exclusive source mode used for this response.",
    },
    "FeatureStatus": {
        "type": "string",
        "enum": [
            "LIVE",
            "INTEGRATION_ONLY",
            "DOCUMENTED",
            "DISABLED",
            "NOT_IMPLEMENTED",
        ],
        "description": "The governed implementation status of a product capability.",
    },
    "MetricUnit": {
        "type": "string",
        "enum": ["count", "currency", "percent", "bps", "ratio", "days", "months"],
        "description": "A wire-level unit used by governed metrics and evidence.",
    },
    "EvidenceId": {
        "type": "string",
        "minLength": 1,
        "description": "A stable identifier that resolves to calculation or artifact evidence.",
    },
    "EvidenceReference": {
        "type": "object",
        "additionalProperties": False,
        "required": ["evidence_id", "feature_status"],
        "properties": {
            "evidence_id": {"$ref": "#/components/schemas/EvidenceId"},
            "feature_status": {"$ref": "#/components/schemas/FeatureStatus"},
            "unit": {
                "anyOf": [
                    {"$ref": "#/components/schemas/MetricUnit"},
                    {"type": "null"},
                ]
            },
        },
    },
    "SourceContext": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "active_mode",
            "configured_mode",
            "snapshot_date",
            "configuration_hash",
            "dataset_hash",
            "dataset_hash_basis",
            "run_id",
            "synthetic",
            "reason",
        ],
        "properties": {
            "active_mode": {"$ref": "#/components/schemas/DataMode"},
            "configured_mode": {"$ref": "#/components/schemas/DataMode"},
            "snapshot_date": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "configuration_hash": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "dataset_hash": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "dataset_hash_basis": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "run_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "synthetic": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
            "reason": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
    },
    "ApiResponseMetadata": {
        "type": "object",
        "required": ["data_mode", "source_context"],
        "properties": {
            "data_mode": {"$ref": "#/components/schemas/DataMode"},
            "source_context": {"$ref": "#/components/schemas/SourceContext"},
        },
        "description": "Metadata injected into every JSON object returned below /api/v1.",
    },
}


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Return a stable JSON representation suitable for hashing and release output."""

    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def enrich_contract(schema: dict[str, Any]) -> dict[str, Any]:
    """Describe middleware-injected metadata and shared governed wire types.

    FastAPI cannot infer fields added by response middleware.  This deterministic
    transformation keeps the generated OpenAPI document honest without duplicating
    those fields on every route implementation.
    """

    enriched = copy.deepcopy(schema)
    component_schemas = enriched.setdefault("components", {}).setdefault("schemas", {})
    component_schemas.update(copy.deepcopy(STRICT_CONTRACT_SCHEMAS))

    metadata_ref = {"$ref": "#/components/schemas/ApiResponseMetadata"}
    for path, path_item in enriched.get("paths", {}).items():
        if not path.startswith("/api/v1") or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            for status, response in operation.get("responses", {}).items():
                if str(status) == "204" or not isinstance(response, dict):
                    continue
                media = response.get("content", {}).get("application/json")
                if not isinstance(media, dict) or not isinstance(media.get("schema"), dict):
                    continue
                original = media["schema"]
                if metadata_ref in original.get("allOf", []):
                    continue
                media["schema"] = {"allOf": [original, copy.deepcopy(metadata_ref)]}
    return enriched


def validate_contract(schema: dict[str, Any]) -> dict[str, Any]:
    """Validate versioning, operation identifiers, and absence of stubbed HTTP 501s."""

    errors: list[str] = []
    operation_ids: list[str] = []
    operations = 0
    api_v1_operations = 0
    for path, path_item in sorted(schema.get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue
        for method, operation in sorted(path_item.items()):
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            operations += 1
            if path.startswith("/api/v1/"):
                api_v1_operations += 1
                if not operation.get("operationId"):
                    errors.append(f"{method.upper()} {path} has no operationId")
            operation_id = operation.get("operationId")
            if operation_id:
                operation_ids.append(str(operation_id))
            responses = operation.get("responses", {})
            if "501" in responses or 501 in responses:
                errors.append(f"{method.upper()} {path} declares HTTP 501")
            if path.startswith("/api/v1"):
                for status, response in responses.items():
                    if str(status) == "204" or not isinstance(response, dict):
                        continue
                    media = response.get("content", {}).get("application/json")
                    if not isinstance(media, dict):
                        continue
                    all_of = media.get("schema", {}).get("allOf", [])
                    metadata_ref = {"$ref": "#/components/schemas/ApiResponseMetadata"}
                    if metadata_ref not in all_of:
                        errors.append(
                            f"{method.upper()} {path} response {status} omits strict API metadata"
                        )

    duplicates = sorted({item for item in operation_ids if operation_ids.count(item) > 1})
    if duplicates:
        errors.append(f"Duplicate operationId values: {', '.join(duplicates)}")
    if not api_v1_operations:
        errors.append("No versioned /api/v1 operations were found")
    if schema.get("info", {}).get("title") != "nAIM Portfolio Intelligence Workbench API":
        errors.append("OpenAPI info.title does not use the canonical nAIM identity")
    missing_shared_schemas = sorted(
        set(STRICT_CONTRACT_SCHEMAS)
        - set(schema.get("components", {}).get("schemas", {}))
    )
    if missing_shared_schemas:
        errors.append(f"Missing shared contract schemas: {', '.join(missing_shared_schemas)}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "path_count": len(schema.get("paths", {})),
        "operation_count": operations,
        "api_v1_operation_count": api_v1_operations,
        "operation_id_count": len(set(operation_ids)),
        "declared_http_501_count": 0
        if not any("HTTP 501" in error for error in errors)
        else sum("HTTP 501" in error for error in errors),
    }


def generate(
    contract_path: Path = DEFAULT_CONTRACT, evidence_path: Path = DEFAULT_EVIDENCE
) -> dict[str, Any]:
    """Write the contract and its compact validation evidence."""

    schema = enrich_contract(app.openapi())
    contract = canonical_bytes(schema)
    validation = validate_contract(schema)
    resolved_contract = contract_path.resolve()
    validation["contract"] = (
        resolved_contract.relative_to(REPOSITORY_ROOT).as_posix()
        if resolved_contract.is_relative_to(REPOSITORY_ROOT)
        else resolved_contract.name
    )
    validation["sha256"] = hashlib.sha256(contract).hexdigest()
    if validation["status"] != "PASS":
        raise ValueError("; ".join(validation["errors"]))

    contract_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_bytes(contract)
    evidence_path.write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return validation


def check(
    contract_path: Path = DEFAULT_CONTRACT, evidence_path: Path = DEFAULT_EVIDENCE
) -> dict[str, Any]:
    """Fail when checked-in contract outputs drift from the current backend schema."""

    schema = enrich_contract(app.openapi())
    contract = canonical_bytes(schema)
    validation = validate_contract(schema)
    resolved_contract = contract_path.resolve()
    validation["contract"] = (
        resolved_contract.relative_to(REPOSITORY_ROOT).as_posix()
        if resolved_contract.is_relative_to(REPOSITORY_ROOT)
        else resolved_contract.name
    )
    validation["sha256"] = hashlib.sha256(contract).hexdigest()
    if validation["status"] != "PASS":
        raise ValueError("; ".join(validation["errors"]))

    expected_evidence = canonical_bytes(validation)
    if not contract_path.is_file() or contract_path.read_bytes() != contract:
        raise ValueError(
            f"OpenAPI contract drift: run {Path(__file__).name} to refresh {contract_path}"
        )
    if not evidence_path.is_file() or evidence_path.read_bytes() != expected_evidence:
        raise ValueError(
            f"OpenAPI validation evidence drift: run {Path(__file__).name} to refresh "
            f"{evidence_path}"
        )
    return validation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify checked-in outputs without changing files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validation = (
        check(args.output, args.evidence)
        if args.check
        else generate(args.output, args.evidence)
    )
    print(json.dumps(validation, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
