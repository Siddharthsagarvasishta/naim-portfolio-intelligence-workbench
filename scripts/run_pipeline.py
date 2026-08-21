#!/usr/bin/env python3
"""Run the deterministic nAIM data pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from naim_risk.config import REPOSITORY_ROOT, load_config
from naim_risk.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        default="default",
        choices=["test", "small", "default", "medium", "large"],
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--data-root", type=Path, default=REPOSITORY_ROOT / "data")
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args()
    result = run_pipeline(
        load_config(args.profile, seed=args.seed, data_root=args.data_root),
        persist=not args.no_persist,
    )
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "profile": args.profile,
                "validation_status": result.validation.status,
                "publication_allowed": result.validation.publication_allowed,
                "row_counts": result.manifest["row_counts"],
                "storage_engine": result.manifest["storage_engine"],
                "manifest": str(result.paths.get("manifest", "")),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
