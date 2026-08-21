#!/usr/bin/env python3
"""Independent-style registry and governance metadata validation."""

from __future__ import annotations

import json

from naim_risk.config import REPOSITORY_ROOT


def main() -> None:
    registry_path = REPOSITORY_ROOT / "models" / "model_registry.json"
    feature_path = REPOSITORY_ROOT / "models" / "feature_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    features = json.loads(feature_path.read_text(encoding="utf-8"))
    required = {
        "model_id",
        "use_case",
        "version",
        "algorithm",
        "approved_use",
        "prohibited_use",
        "limitations",
        "status",
    }
    failures = []
    for model in registry["models"]:
        missing = required.difference(model)
        if missing:
            failures.append({"model_id": model.get("model_id"), "missing_fields": sorted(missing)})
        if model["status"] == "documented_integration" and model.get("artefact_path"):
            failures.append(
                {
                    "model_id": model["model_id"],
                    "issue": "Documented integrations must not claim a trained artefact.",
                }
            )
    if features.get("protected_attributes_used") is not False:
        failures.append({"issue": "Protected-attribute prohibition not declared."})
    result = {
        "status": "PASS" if not failures else "FAIL",
        "model_count": len(registry["models"]),
        "feature_count": len(features["features"]),
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
