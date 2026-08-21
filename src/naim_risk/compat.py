"""Explicit compatibility adapters for retired environment variable names."""

from __future__ import annotations

import os
import warnings
from collections.abc import Iterable

# Compatibility-only references are deliberately isolated here so active code uses
# the canonical nAIM environment contract. Remove these aliases in the next major release.
LEGACY_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "NAIM_DATASET_PROFILE": ("AEGIS_DATASET_PROFILE", "AEGIS_PROFILE"),
    "NAIM_DATA_DIR": ("AEGIS_DATA_DIR", "AEGIS_DATA_ROOT"),
    "NAIM_RANDOM_SEED": ("AEGIS_RANDOM_SEED",),
    "NAIM_LOG_LEVEL": ("AEGIS_LOG_LEVEL",),
    "NAIM_ALLOWED_ORIGINS": ("AEGIS_ALLOWED_ORIGINS", "AEGIS_CORS_ORIGINS"),
}


def environment_value(canonical_name: str, default: str | None = None) -> str | None:
    """Read a canonical setting, falling back to warned legacy aliases."""

    canonical_value = os.getenv(canonical_name)
    if canonical_value is not None:
        return canonical_value

    for legacy_name in LEGACY_ENV_ALIASES.get(canonical_name, ()):
        legacy_value = os.getenv(legacy_name)
        if legacy_value is None:
            continue
        warnings.warn(
            f"{legacy_name} is deprecated; use {canonical_name} instead.",
            FutureWarning,
            stacklevel=2,
        )
        return legacy_value
    return default


def configured_legacy_environment() -> Iterable[tuple[str, str]]:
    """Yield configured legacy/canonical pairs for diagnostics."""

    for canonical_name, legacy_names in LEGACY_ENV_ALIASES.items():
        if os.getenv(canonical_name) is not None:
            continue
        for legacy_name in legacy_names:
            if os.getenv(legacy_name) is not None:
                yield legacy_name, canonical_name
                break
