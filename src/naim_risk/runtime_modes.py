"""Strict data-source modes and portable snapshot provenance for nAIM."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from naim_risk.config import NaimConfig
from naim_risk.storage import latest_manifest


class DataMode(StrEnum):
    """Mutually exclusive runtime data-source modes."""

    LIVE = "LIVE"
    DEMO = "DEMO"
    OFFLINE_SNAPSHOT = "OFFLINE_SNAPSHOT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class SourceContext:
    """Safe provenance fields that may be displayed in the API and UI."""

    active_mode: DataMode
    configured_mode: DataMode
    snapshot_date: str | None
    configuration_hash: str | None
    dataset_hash: str | None
    dataset_hash_basis: str | None
    run_id: str | None
    synthetic: bool | None
    reason: str | None

    def public(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "active_mode": self.active_mode.value,
            "configured_mode": self.configured_mode.value,
        }


def data_mode_from_environment() -> DataMode:
    """Resolve the selected mode without silently accepting misspellings."""

    raw_mode = os.getenv("NAIM_DATA_MODE", "OFFLINE_SNAPSHOT").strip().upper()
    try:
        return DataMode(raw_mode)
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in DataMode)
        raise ValueError(f"NAIM_DATA_MODE must be one of: {allowed}") from exc


def _portable_manifest_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return stable manifest fields without host paths or wall-clock timestamps."""

    excluded = {"paths", "generation_timestamp", "completion_timestamp", "duration_seconds"}
    return {key: value for key, value in manifest.items() if key not in excluded}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=16)
def _dataset_hash_cached(
    manifest_path_text: str,
    manifest_mtime_ns: int,
    data_root_text: str,
) -> tuple[str, str]:
    del manifest_mtime_ns
    manifest_path = Path(manifest_path_text)
    data_root = Path(data_root_text).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    component_hashes: list[tuple[str, int, str]] = []
    for logical_name, raw_path in sorted(manifest.get("paths", {}).items()):
        if not (logical_name.startswith("validated.") or logical_name.startswith("mart.")):
            continue
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = manifest_path.parent / candidate
        candidate = candidate.resolve()
        if not candidate.is_relative_to(data_root) or not candidate.is_file():
            continue
        component_hashes.append((logical_name, candidate.stat().st_size, _sha256_file(candidate)))
    if component_hashes:
        payload = json.dumps(component_hashes, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest(), "validated-and-mart-files"
    payload = json.dumps(
        _portable_manifest_payload(manifest), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), "portable-run-manifest"


def dataset_hash(manifest_path: Path, data_root: Path) -> tuple[str, str]:
    """Hash persisted analytical content, with a portable-manifest fallback."""

    return _dataset_hash_cached(
        str(manifest_path.resolve()),
        manifest_path.stat().st_mtime_ns,
        str(data_root.resolve()),
    )


def source_context(config: NaimConfig, mode: DataMode | None = None) -> SourceContext:
    """Build an honest data-mode context from the selected persisted run."""

    configured_mode = mode or data_mode_from_environment()
    if configured_mode is DataMode.UNAVAILABLE:
        return SourceContext(
            active_mode=DataMode.UNAVAILABLE,
            configured_mode=configured_mode,
            snapshot_date=None,
            configuration_hash=config.config_hash,
            dataset_hash=None,
            dataset_hash_basis=None,
            run_id=None,
            synthetic=None,
            reason="The data source was explicitly disabled by NAIM_DATA_MODE.",
        )

    manifest_path = latest_manifest(config.data_root)
    if manifest_path is None:
        if configured_mode is DataMode.DEMO:
            deterministic_hash = hashlib.sha256(
                f"{config.config_hash}:{config.seed}:{config.profile.name}".encode()
            ).hexdigest()
            return SourceContext(
                active_mode=DataMode.DEMO,
                configured_mode=configured_mode,
                snapshot_date=None,
                configuration_hash=config.config_hash,
                dataset_hash=deterministic_hash,
                dataset_hash_basis="deterministic-demo-configuration",
                run_id=None,
                synthetic=True,
                reason="No persisted snapshot is present; deterministic demo generation is active.",
            )
        return SourceContext(
            active_mode=DataMode.UNAVAILABLE,
            configured_mode=configured_mode,
            snapshot_date=None,
            configuration_hash=config.config_hash,
            dataset_hash=None,
            dataset_hash_basis=None,
            run_id=None,
            synthetic=None,
            reason=f"{configured_mode.value} requires a persisted repository dataset.",
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        content_hash, hash_basis = dataset_hash(manifest_path, config.data_root)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return SourceContext(
            active_mode=DataMode.UNAVAILABLE,
            configured_mode=configured_mode,
            snapshot_date=None,
            configuration_hash=config.config_hash,
            dataset_hash=None,
            dataset_hash_basis=None,
            run_id=None,
            synthetic=None,
            reason=f"Persisted dataset provenance could not be verified: {type(exc).__name__}.",
        )

    manifest_configuration_hash = str(manifest.get("configuration_hash") or "")
    if manifest_configuration_hash != config.config_hash:
        return SourceContext(
            active_mode=DataMode.UNAVAILABLE,
            configured_mode=configured_mode,
            snapshot_date=str(manifest.get("maximum_data_date") or "") or None,
            configuration_hash=manifest_configuration_hash or None,
            dataset_hash=content_hash,
            dataset_hash_basis=hash_basis,
            run_id=str(manifest.get("run_id") or "") or None,
            synthetic=bool(manifest.get("synthetic_data")),
            reason=(
                "The persisted dataset configuration hash does not match the current "
                "governed configuration. Regenerate and republish the snapshot before use."
            ),
        )

    if not manifest.get("publication_allowed"):
        return SourceContext(
            active_mode=DataMode.UNAVAILABLE,
            configured_mode=configured_mode,
            snapshot_date=str(manifest.get("maximum_data_date") or "") or None,
            configuration_hash=str(manifest.get("configuration_hash") or config.config_hash),
            dataset_hash=content_hash,
            dataset_hash_basis=hash_basis,
            run_id=str(manifest.get("run_id") or "") or None,
            synthetic=bool(manifest.get("synthetic_data")),
            reason="The selected dataset did not pass its publication gate.",
        )

    return SourceContext(
        active_mode=configured_mode,
        configured_mode=configured_mode,
        snapshot_date=str(manifest.get("maximum_data_date") or "") or None,
        configuration_hash=str(manifest.get("configuration_hash") or config.config_hash),
        dataset_hash=content_hash,
        dataset_hash_basis=hash_basis,
        run_id=str(manifest.get("run_id") or "") or None,
        synthetic=bool(manifest.get("synthetic_data")),
        reason=None,
    )


def clear_runtime_mode_caches() -> None:
    """Clear content hashes between isolated tests or deliberate dataset switches."""

    _dataset_hash_cached.cache_clear()
