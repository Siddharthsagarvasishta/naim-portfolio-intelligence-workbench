"""Strict source loading for the read-only nAIM public companion."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ALLOWED_DATA_MODES = frozenset({"LIVE", "DEMO", "OFFLINE_SNAPSHOT", "UNAVAILABLE"})
PUBLIC_API_PATH = "api/v1/public-evidence"
PUBLIC_HEALTH_PATH = "api/v1/health"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT = Path(__file__).resolve().parent / "evidence" / "public_evidence_snapshot.json"
DEFAULT_WORKBOOK = REPOSITORY_ROOT / "outputs" / "nAIM_Portfolio_Intelligence_Workbench.xlsx"
FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "account_id",
        "customer_id",
        "email",
        "phone",
        "address",
        "password",
        "secret",
        "access_token",
        "refresh_token",
    }
)


class PublicEvidenceError(ValueError):
    """Raised when a public source is missing, ambiguous, or not approved."""


@dataclass(frozen=True)
class PublicSourceResult:
    """Validated evidence and source-health metadata."""

    evidence: dict[str, Any] | None
    mode: str
    health: str
    detail: str
    source_label: str


def _iter_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key).lower())
            keys.extend(_iter_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_iter_keys(child))
    return keys


def _validate_public_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != "1.0.0":
        raise PublicEvidenceError("Unsupported public-evidence schema version")
    if payload.get("product") != "nAIM Portfolio Intelligence Workbench":
        raise PublicEvidenceError("Unexpected product identity")
    if payload.get("synthetic_data") is not True:
        raise PublicEvidenceError("Public evidence must be explicitly synthetic")
    validation = payload.get("validation")
    if not isinstance(validation, dict):
        raise PublicEvidenceError("Public evidence has no validation block")
    if validation.get("publication_allowed") is not True:
        raise PublicEvidenceError("Evidence publication is not approved")
    if validation.get("data_quality_status") != "PASS":
        raise PublicEvidenceError("Evidence did not pass the data-quality gate")
    data_mode = payload.get("data_mode")
    if data_mode not in ALLOWED_DATA_MODES:
        raise PublicEvidenceError(f"Unsupported data mode: {data_mode!r}")
    forbidden = sorted(set(_iter_keys(payload)).intersection(FORBIDDEN_PUBLIC_KEYS))
    if forbidden:
        raise PublicEvidenceError(f"Public evidence contains forbidden raw-data keys: {forbidden}")
    story = payload.get("portfolio_story")
    if not isinstance(story, dict) or story.get("observed_change_bps") is None:
        raise PublicEvidenceError("Public evidence has no governed portfolio story")
    return payload


def _read_snapshot(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PublicEvidenceError(f"Offline evidence snapshot is unavailable: {exc}") from exc
    digest_path = path.with_suffix(path.suffix + ".sha256")
    if not digest_path.exists():
        raise PublicEvidenceError("Offline evidence checksum is unavailable")
    expected = digest_path.read_text(encoding="utf-8").strip().split()[0]
    actual = hashlib.sha256(raw).hexdigest()
    if expected != actual:
        raise PublicEvidenceError("Offline evidence checksum does not match")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PublicEvidenceError("Offline evidence is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise PublicEvidenceError("Offline evidence must be a JSON object")
    return _validate_public_evidence(payload)


def _safe_api_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PublicEvidenceError("Public API base URL must be an http(s) origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise PublicEvidenceError("Public API base URL must not contain credentials or query data")
    return value.rstrip("/") + "/"


def _read_api_json(base_url: str, path: str, timeout_seconds: float) -> dict[str, Any]:
    url = urljoin(_safe_api_base_url(base_url), path)
    request = Request(
        url, headers={"Accept": "application/json", "User-Agent": "nAIM-public-demo/1"}
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            if response.status != 200:
                raise PublicEvidenceError(f"Public API returned HTTP {response.status}")
            payload = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise PublicEvidenceError(f"Public API is unavailable: {exc}") from exc
    if not isinstance(payload, dict):
        raise PublicEvidenceError("Public API returned a non-object payload")
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise PublicEvidenceError("Public API returned an invalid evidence envelope")
    return data


def load_public_evidence(
    *,
    source_mode: str | None = None,
    snapshot_path: Path | None = None,
    api_base_url: str | None = None,
    timeout_seconds: float = 4.0,
) -> PublicSourceResult:
    """Load one explicit source; API mode never falls back to the offline snapshot."""

    requested = (source_mode or os.getenv("NAIM_PUBLIC_DEMO_MODE", "OFFLINE_SNAPSHOT")).upper()
    if requested == "OFFLINE_SNAPSHOT":
        selected = snapshot_path or Path(
            os.getenv("NAIM_PUBLIC_EVIDENCE_PATH", str(DEFAULT_SNAPSHOT))
        )
        try:
            evidence = _read_snapshot(selected)
        except PublicEvidenceError as exc:
            return PublicSourceResult(None, "UNAVAILABLE", "FAIL", str(exc), "offline snapshot")
        return PublicSourceResult(
            evidence,
            "OFFLINE_SNAPSHOT",
            "PASS",
            "Checksum and publication controls passed.",
            "validated offline evidence snapshot",
        )
    if requested == "API":
        base_url = api_base_url or os.getenv("NAIM_PUBLIC_API_BASE_URL", "")
        if not base_url:
            return PublicSourceResult(
                None,
                "UNAVAILABLE",
                "FAIL",
                "NAIM_PUBLIC_API_BASE_URL is required in API mode.",
                "governed API",
            )
        try:
            evidence = _validate_public_evidence(
                _read_api_json(base_url, PUBLIC_API_PATH, timeout_seconds)
            )
        except PublicEvidenceError as exc:
            return PublicSourceResult(None, "UNAVAILABLE", "FAIL", str(exc), "governed API")
        return PublicSourceResult(
            evidence,
            str(evidence["data_mode"]),
            "PASS",
            "Governed public-evidence endpoint responded and passed validation.",
            "governed API",
        )
    return PublicSourceResult(
        None,
        "UNAVAILABLE",
        "FAIL",
        "NAIM_PUBLIC_DEMO_MODE must be API or OFFLINE_SNAPSHOT.",
        "unconfigured source",
    )


def probe_api_health(base_url: str, *, timeout_seconds: float = 2.0) -> dict[str, str]:
    """Read the public health endpoint without sending credentials."""

    try:
        payload = _read_api_json(base_url, PUBLIC_HEALTH_PATH, timeout_seconds)
    except PublicEvidenceError as exc:
        return {"status": "UNAVAILABLE", "detail": str(exc)}
    status = str(payload.get("status", "UNKNOWN")).upper()
    return {"status": status, "detail": "Public health endpoint responded."}


def find_sample_workbook(explicit_path: Path | None = None) -> Path | None:
    """Return the validated public workbook only; historical artifacts are never substituted."""

    configured = explicit_path or Path(
        os.getenv("NAIM_PUBLIC_SAMPLE_EXCEL_PATH", str(DEFAULT_WORKBOOK))
    )
    if not configured.is_file() or configured.suffix.lower() != ".xlsx":
        return None
    return configured
