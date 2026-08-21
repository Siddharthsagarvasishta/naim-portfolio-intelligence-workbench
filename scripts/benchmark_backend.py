#!/usr/bin/env python3
"""Record honest local timings for repeated analytical service calls."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from naim_risk.config import REPOSITORY_ROOT, load_config
from naim_risk.service import WorkbenchService


def _measure(callable_object: object, repetitions: int) -> dict[str, float]:
    timings = []
    for _ in range(repetitions):
        started = time.perf_counter()
        callable_object()
        timings.append((time.perf_counter() - started) * 1000)
    ordered = sorted(timings)
    percentile_index = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return {
        "median_ms": statistics.median(timings),
        "p95_ms": ordered[percentile_index],
        "minimum_ms": min(timings),
        "maximum_ms": max(timings),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="test", choices=["test", "small", "default"])
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--data-root", type=Path, default=REPOSITORY_ROOT / "data")
    args = parser.parse_args()
    service = WorkbenchService(load_config(args.profile, data_root=args.data_root))
    service.command_centre()
    service.root_cause()
    service.partners()
    result = {
        "timestamp": datetime.now(UTC).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "profile": args.profile,
        "account_month_rows": service.data.manifest["row_counts"]["monthly_account_performance"],
        "repetitions": args.repetitions,
        "results": {
            "command_centre_warm": _measure(service.command_centre, args.repetitions),
            "root_cause_warm": _measure(service.root_cause, args.repetitions),
            "partner_analytics_warm": _measure(service.partners, args.repetitions),
        },
    }
    target = args.data_root / "benchmarks"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"backend-{args.profile}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({**result, "path": str(path)}, indent=2))


if __name__ == "__main__":
    main()
