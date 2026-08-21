"""Allowlisted commentary providers and post-generation numerical verification."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class CommentaryEvidence:
    reporting_period: str
    comparison_period: str
    metric_values: Mapping[str, float | None]
    validated_movements: Mapping[str, float | None]
    root_cause_contributions: Mapping[str, Any]
    alert_status: Sequence[Mapping[str, Any]]
    statistical_confidence: Mapping[str, str]
    caveats: Sequence[str]
    recommended_investigation_steps: Sequence[str]
    data_quality_status: str

    def allowlisted_dict(self) -> dict[str, Any]:
        """Return only approved aggregate evidence fields."""

        return asdict(self)


@dataclass
class CommentaryResult:
    text: str
    provider: str
    model_name: str
    prompt_version: str
    generation_timestamp: str
    verification_status: str
    unsupported_numbers: list[float] = field(default_factory=list)
    metric_ids: list[str] = field(default_factory=list)
    draft_requires_human_review: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class CommentaryProvider(Protocol):
    def generate(self, evidence: CommentaryEvidence) -> CommentaryResult:
        """Convert validated aggregate evidence to language without recalculation."""


def _flatten_numbers(value: Any) -> list[float]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, Mapping):
        result: list[float] = []
        for nested in value.values():
            result.extend(_flatten_numbers(nested))
        return result
    if isinstance(value, (list, tuple)):
        result = [float(len(value))]
        for nested in value:
            result.extend(_flatten_numbers(nested))
        return result
    return []


def verify_numerical_claims(text: str, evidence: CommentaryEvidence) -> dict[str, Any]:
    """Reject numbers not traceable to the allowlisted evidence object."""

    cleaned = re.sub(r"\b\d{4}-\d{2}(?:-\d{2})?\b", "", text)
    extracted = [
        float(value)
        for value in re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?![A-Za-z+])", cleaned)
    ]
    base = _flatten_numbers(evidence.allowlisted_dict())
    allowed = {0.0, 1.0, 12.0, 30.0, 60.0, 90.0, 100.0, 1000.0, 10000.0}
    for value in base:
        for transformed in (value, value * 100.0, value * 10_000.0):
            allowed.add(round(float(transformed), 0))
            allowed.add(round(float(transformed), 1))
            allowed.add(round(float(transformed), 2))
    unsupported = [
        value
        for value in extracted
        if not any(abs(value - allowed_value) <= 0.011 for allowed_value in allowed)
    ]
    return {
        "status": "PASS" if not unsupported else "REJECTED",
        "extracted_numbers": extracted,
        "unsupported_numbers": unsupported,
    }


class DeterministicTemplateProvider:
    """Default offline provider that uses no external model or raw records."""

    provider_name = "deterministic-template"
    model_name = "nAIM Template v1"
    prompt_version = "commentary-contract-1.0.0"

    def generate(self, evidence: CommentaryEvidence) -> CommentaryResult:
        metric_ids = sorted(evidence.metric_values)
        loss_value = evidence.metric_values.get("ANNUALISED_NET_LOSS_RATE")
        loss_move = evidence.validated_movements.get("ANNUALISED_NET_LOSS_RATE")
        delinquency = evidence.metric_values.get("DELINQUENCY_30_ACCOUNT_RATE")
        profit = evidence.metric_values.get("EXPECTED_PROFIT")
        driver = evidence.root_cause_contributions.get("primary_driver")
        contribution = evidence.root_cause_contributions.get("contribution_share")
        alert_count = len(evidence.alert_status)
        loss_text = "N/A" if loss_value is None else f"{loss_value * 100:.2f}%"
        loss_move_text = "N/A" if loss_move is None else f"{loss_move * 10_000:.1f} bps"
        delinquency_text = "N/A" if delinquency is None else f"{delinquency * 100:.2f}%"
        profit_text = "N/A" if profit is None else f"{profit:.2f}"
        contribution_text = (
            "N/A" if not isinstance(contribution, (int, float)) else f"{contribution * 100:.1f}%"
        )
        primary_driver = str(driver or "No single validated driver")
        investigation = (
            evidence.recommended_investigation_steps[0]
            if evidence.recommended_investigation_steps
            else "Continue governed monitoring."
        )
        caveat = (
            evidence.caveats[0]
            if evidence.caveats
            else "No material analytical caveat beyond the synthetic-data limitation."
        )
        text = (
            f"Portfolio position — For {evidence.reporting_period}, the annualised net loss rate was "
            f"{loss_text}, 30+ delinquency was {delinquency_text}, and expected profit was {profit_text}. "
            f"[ANNUALISED_NET_LOSS_RATE; DELINQUENCY_30_ACCOUNT_RATE; EXPECTED_PROFIT]\n\n"
            f"Material movements — Annualised net loss moved by {loss_move_text} versus "
            f"{evidence.comparison_period}. [ANNUALISED_NET_LOSS_RATE]\n\n"
            f"Primary drivers — The strongest associational lens was {primary_driver}, representing "
            f"{contribution_text} of the reconciled movement. This is not a causal conclusion.\n\n"
            f"Strategy implications — No automatic credit-policy action is proposed. Review the exact "
            f"strategy guardrails and approval path before any controlled change.\n\n"
            f"Emerging risks — {alert_count} governed alerts are open in the supplied evidence.\n\n"
            f"Recommended investigation — {investigation}\n\n"
            f"Data or methodology caveats — Data quality status is {evidence.data_quality_status}. "
            f"{caveat}\n\nDraft generated from validated structured findings; human review required."
        )
        verification = verify_numerical_claims(text, evidence)
        if verification["status"] != "PASS":
            text = (
                "Commentary rejected because one or more numerical statements were not supported by "
                "the validated evidence contract."
            )
        return CommentaryResult(
            text=text,
            provider=self.provider_name,
            model_name=self.model_name,
            prompt_version=self.prompt_version,
            generation_timestamp=datetime.now(UTC).isoformat(),
            verification_status=verification["status"],
            unsupported_numbers=verification["unsupported_numbers"],
            metric_ids=metric_ids,
        )


class MockCommentaryProvider:
    """Test provider that can intentionally return supported or unsupported claims."""

    def __init__(self, text: str) -> None:
        self.text = text

    def generate(self, evidence: CommentaryEvidence) -> CommentaryResult:
        verification = verify_numerical_claims(self.text, evidence)
        return CommentaryResult(
            text=self.text
            if verification["status"] == "PASS"
            else "Rejected unsupported commentary.",
            provider="mock",
            model_name="mock",
            prompt_version="test",
            generation_timestamp=datetime.now(UTC).isoformat(),
            verification_status=verification["status"],
            unsupported_numbers=verification["unsupported_numbers"],
            metric_ids=sorted(evidence.metric_values),
        )


def evidence_json(evidence: CommentaryEvidence) -> str:
    """Serialise the exact allowlisted payload an optional provider may receive."""

    return json.dumps(evidence.allowlisted_dict(), sort_keys=True, separators=(",", ":"))
