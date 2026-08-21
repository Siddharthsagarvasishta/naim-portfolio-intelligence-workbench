"""Deprecated compatibility shim for the canonical :mod:`naim_risk` package."""

from __future__ import annotations

import warnings
from importlib import import_module
from sys import modules

from naim_risk import NaimConfig, __version__, load_config

warnings.warn(
    "aegis_risk is deprecated; import naim_risk instead.",
    FutureWarning,
    stacklevel=2,
)

# Compatibility-only module aliases preserve object identity without retaining
# a second analytical implementation. Configuration has a tiny wrapper because
# its historical class name also needs to remain importable.
_SUPPORTED_SUBMODULES = (
    "alerts",
    "alerts.engine",
    "baskets",
    "baskets.engine",
    "capacity",
    "capacity.analysis",
    "commentary",
    "commentary.providers",
    "common",
    "common.math",
    "cross_domain",
    "cross_domain.analytics",
    "data_generation",
    "data_generation.generator",
    "exports",
    "exports.packages",
    "forecasting",
    "forecasting.scenarios",
    "governance",
    "governance.drift",
    "metrics",
    "metrics.core",
    "network",
    "network.analysis",
    "peer",
    "peer.analysis",
    "pipeline",
    "ratings",
    "ratings.engine",
    "root_cause",
    "root_cause.decomposition",
    "segmentation",
    "segmentation.business_rules",
    "segmentation.statistical",
    "service",
    "storage",
    "strategies",
    "strategies.comparison",
    "transformations",
    "transformations.marts",
    "types",
    "validation",
    "validation.gate",
    "vintage",
    "vintage.analysis",
)
for _module_name in _SUPPORTED_SUBMODULES:
    modules[f"aegis_risk.{_module_name}"] = import_module(f"naim_risk.{_module_name}")

AegisConfig = NaimConfig

__all__ = ["AegisConfig", "NaimConfig", "__version__", "load_config"]
