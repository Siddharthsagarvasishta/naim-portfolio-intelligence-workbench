"""Deprecated configuration aliases for legacy imports."""

from __future__ import annotations

import warnings

from naim_risk.config import (
    CONFIG_ROOT,
    MODEL_ROOT,
    REPOSITORY_ROOT,
    DatasetProfile,
    NaimConfig,
    load_config,
    metric_lookup,
)

warnings.warn(
    "aegis_risk.config is deprecated; import naim_risk.config instead.",
    FutureWarning,
    stacklevel=2,
)

AegisConfig = NaimConfig

__all__ = [
    "AegisConfig",
    "CONFIG_ROOT",
    "DatasetProfile",
    "MODEL_ROOT",
    "NaimConfig",
    "REPOSITORY_ROOT",
    "load_config",
    "metric_lookup",
]
