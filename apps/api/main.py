"""Compatibility import for the canonical :mod:`naim_risk.api` application."""

from __future__ import annotations

import sys

from naim_risk import api as _canonical_api

# Preserve module identity for integrations that still import this historical path.
sys.modules[__name__] = _canonical_api
