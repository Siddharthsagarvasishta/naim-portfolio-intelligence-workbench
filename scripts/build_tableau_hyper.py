"""Build the governed Tableau Hyper derivative from the configured dataset profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from naim_risk.config import load_config
from naim_risk.service import WorkbenchService
from naim_risk.tableau import generate_hyper_extract


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="default")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/tableau/nAIM_Portfolio_Intelligence.hyper"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    service = WorkbenchService(load_config(args.profile))
    result = generate_hyper_extract(service, output_path=args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
