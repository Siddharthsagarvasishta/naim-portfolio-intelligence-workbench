from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from naim_risk.capabilities import capability_registry
from naim_risk.config import load_config
from naim_risk.metrics.governance import data_source_diagnostics
from naim_risk.runtime_modes import (
    DataMode,
    clear_runtime_mode_caches,
    data_mode_from_environment,
    source_context,
)


def _write_manifest(
    data_root: Path,
    *,
    configuration_hash: str = "abc123",
    publication_allowed: bool = True,
) -> Path:
    table_path = data_root / "validated" / "run-1" / "accounts.parquet"
    table_path.parent.mkdir(parents=True)
    table_path.write_bytes(b"validated analytical bytes")
    manifest_path = data_root / "manifests" / "run-1" / "run_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "configuration_hash": configuration_hash,
                "maximum_data_date": "2025-12-01",
                "publication_allowed": publication_allowed,
                "synthetic_data": True,
                "paths": {"validated.accounts": str(table_path)},
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_offline_snapshot_exposes_portable_provenance(tmp_path: Path) -> None:
    config = load_config("test", data_root=tmp_path)
    _write_manifest(tmp_path, configuration_hash=config.config_hash)
    clear_runtime_mode_caches()
    context = source_context(config, DataMode.OFFLINE_SNAPSHOT)

    assert context.active_mode is DataMode.OFFLINE_SNAPSHOT
    assert context.snapshot_date == "2025-12-01"
    assert context.configuration_hash == config.config_hash
    assert context.dataset_hash
    assert context.dataset_hash_basis == "validated-and-mart-files"
    assert str(tmp_path) not in json.dumps(context.public())


def test_dataset_hash_changes_when_validated_content_changes(tmp_path: Path) -> None:
    config = load_config("test", data_root=tmp_path)
    manifest_path = _write_manifest(tmp_path, configuration_hash=config.config_hash)
    first = source_context(config, DataMode.OFFLINE_SNAPSHOT).dataset_hash
    table_path = tmp_path / "validated" / "run-1" / "accounts.parquet"
    table_path.write_bytes(b"changed analytical bytes")
    manifest_path.touch()
    second = source_context(config, DataMode.OFFLINE_SNAPSHOT).dataset_hash
    assert first != second
    assert second != hashlib.sha256(table_path.read_bytes()).hexdigest()


def test_missing_offline_snapshot_is_unavailable_but_demo_is_deterministic(
    tmp_path: Path,
) -> None:
    config = load_config("test", seed=123, data_root=tmp_path)
    offline = source_context(config, DataMode.OFFLINE_SNAPSHOT)
    demo = source_context(config, DataMode.DEMO)
    assert offline.active_mode is DataMode.UNAVAILABLE
    assert "requires a persisted" in str(offline.reason)
    assert demo.active_mode is DataMode.DEMO
    assert demo.dataset_hash
    assert demo.synthetic is True


def test_failed_publication_gate_forces_unavailable(tmp_path: Path) -> None:
    config = load_config("test", data_root=tmp_path)
    _write_manifest(
        tmp_path,
        configuration_hash=config.config_hash,
        publication_allowed=False,
    )
    context = source_context(config, DataMode.LIVE)
    assert context.configured_mode is DataMode.LIVE
    assert context.active_mode is DataMode.UNAVAILABLE
    assert "publication gate" in str(context.reason)


def test_configuration_mismatch_never_activates_persisted_snapshot(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, configuration_hash="foreign-configuration")
    config = load_config("test", data_root=tmp_path)
    context = source_context(config, DataMode.OFFLINE_SNAPSHOT)
    assert context.configured_mode is DataMode.OFFLINE_SNAPSHOT
    assert context.active_mode is DataMode.UNAVAILABLE
    assert context.configuration_hash == "foreign-configuration"
    assert context.run_id == "run-1"
    assert context.dataset_hash
    assert "does not match" in str(context.reason)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    diagnostics = data_source_diagnostics(
        context=context,
        manifest=manifest,
        stale_after_seconds=86400,
        current_governed_configuration_hash=config.config_hash,
    )
    assert diagnostics["diagnostic_status"] == "UNAVAILABLE"
    assert diagnostics["configured_mode"] == "OFFLINE_SNAPSHOT"
    assert diagnostics["provenance"]["configuration_hash"] == "foreign-configuration"
    assert diagnostics["provenance"]["current_governed_configuration_hash"] == (
        config.config_hash
    )
    assert diagnostics["provenance"]["configuration_match"] is False


def test_data_mode_environment_is_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAIM_DATA_MODE", "demo")
    assert data_mode_from_environment() is DataMode.DEMO
    monkeypatch.setenv("NAIM_DATA_MODE", "hybrid")
    with pytest.raises(ValueError, match="NAIM_DATA_MODE"):
        data_mode_from_environment()


def test_capability_registry_exposes_ordered_status_counts() -> None:
    registry = capability_registry()
    assert registry["product"] == "nAIM Portfolio Intelligence Workbench"
    assert len(registry["data"]) == sum(registry["status_counts"].values())
    assert list(registry["status_counts"]) == registry["allowed_statuses"]
