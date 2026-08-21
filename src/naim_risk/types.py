"""Shared typed containers for pipeline and analytical results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class ValidationCheck:
    check_id: str
    severity: str
    status: str
    affected_rows: int
    business_impact: str
    recommendation: str
    quarantine_location: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "severity": self.severity,
            "status": self.status,
            "affected_rows": int(self.affected_rows),
            "business_impact": self.business_impact,
            "recommendation": self.recommendation,
            "quarantine_location": self.quarantine_location,
            "details": dict(self.details),
        }


@dataclass
class ValidationResult:
    status: str
    quality_score: float
    checks: list[ValidationCheck]
    accepted: dict[str, pd.DataFrame]
    quarantined: dict[str, pd.DataFrame]

    @property
    def publication_allowed(self) -> bool:
        return self.status != "BLOCKED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score": float(self.quality_score),
            "publication_allowed": self.publication_allowed,
            "checks": [check.as_dict() for check in self.checks],
        }


@dataclass
class PipelineData:
    run_id: str
    tables: dict[str, pd.DataFrame]
    marts: dict[str, pd.DataFrame]
    manifest: dict[str, Any]
    validation: ValidationResult
    paths: dict[str, Path] = field(default_factory=dict)
