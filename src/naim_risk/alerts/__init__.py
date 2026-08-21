"""Configurable governed early-warning alerts."""

from .engine import (
    alert_fingerprint,
    build_alert_candidate,
    generate_alerts,
    normalise_selected_scope,
)
from .lifecycle import (
    ALERT_STATUSES,
    AlertLifecycle,
    alert_observation_key,
)

__all__ = [
    "alert_fingerprint",
    "alert_observation_key",
    "ALERT_STATUSES",
    "AlertLifecycle",
    "build_alert_candidate",
    "generate_alerts",
    "normalise_selected_scope",
]
