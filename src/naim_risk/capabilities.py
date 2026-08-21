"""Machine-readable capability truth registry used by the API and frontend."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from naim_risk.config import CONFIG_ROOT


def capability_registry(path: Path | None = None) -> dict[str, Any]:
    """Load the governed JSON-compatible YAML registry without optional parsers."""

    registry_path = path or CONFIG_ROOT / "feature_status.yaml"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    features = registry.get("features")
    if not isinstance(features, list):
        raise ValueError("Capability registry features must be a list")
    counts = Counter(str(feature.get("status")) for feature in features)
    return {
        "schema_version": registry["schema_version"],
        "registry_version": registry["registry_version"],
        "product": registry["product"],
        "description": registry["description"],
        "allowed_statuses": registry["allowed_statuses"],
        "status_definitions": registry["status_definitions"],
        "data": features,
        "status_counts": {status: counts.get(status, 0) for status in registry["allowed_statuses"]},
    }
