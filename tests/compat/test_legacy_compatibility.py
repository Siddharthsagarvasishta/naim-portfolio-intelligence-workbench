from __future__ import annotations

import importlib
import sys
import warnings

from naim_risk.compat import environment_value
from naim_risk.config import NaimConfig


def test_legacy_environment_alias_warns(monkeypatch) -> None:
    monkeypatch.delenv("NAIM_DATASET_PROFILE", raising=False)
    monkeypatch.setenv("AEGIS_DATASET_PROFILE", "test")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert environment_value("NAIM_DATASET_PROFILE") == "test"
    assert any("NAIM_DATASET_PROFILE" in str(item.message) for item in caught)


def test_legacy_package_import_warns_and_exposes_config_alias() -> None:
    sys.modules.pop("aegis_risk", None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        legacy = importlib.import_module("aegis_risk")
    assert legacy.AegisConfig is NaimConfig
    assert any("naim_risk" in str(item.message) for item in caught)


def test_legacy_service_module_is_the_canonical_module() -> None:
    legacy = importlib.import_module("aegis_risk.service")
    canonical = importlib.import_module("naim_risk.service")
    assert legacy is canonical
