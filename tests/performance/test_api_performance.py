from __future__ import annotations

import time

import pytest


@pytest.mark.performance
def test_warm_command_centre_is_below_interactive_target(service):
    service.command_centre()
    started = time.perf_counter()
    service.command_centre()
    elapsed = time.perf_counter() - started
    assert elapsed < 1.5
