#!/usr/bin/env python3
"""Run the live calculated recruiter/demo sequence without a web browser."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from naim_risk.config import REPOSITORY_ROOT, load_config
from naim_risk.service import WorkbenchService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="test", choices=["test", "small", "default"])
    parser.add_argument("--data-root", type=Path, default=REPOSITORY_ROOT / "data")
    args = parser.parse_args()
    service = WorkbenchService(load_config(args.profile, data_root=args.data_root))
    result = service.run_demo()
    root = result["steps"][1]["result"].get("finding") or {}
    strategy = result["steps"][2]["result"]
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "status": result["status"],
                "live_calculations": result["live_calculations"],
                "root_cause": root,
                "strategy_recommendation": strategy["recommendation"],
                "commentary_verification": result["steps"][3]["result"]["verification_status"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
