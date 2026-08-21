#!/usr/bin/env python3
"""Generate live demo exports and a reconciliation evidence snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from naim_risk.config import REPOSITORY_ROOT, load_config
from naim_risk.service import WorkbenchService, json_safe


def evidence_snapshot(service: WorkbenchService) -> dict[str, object]:
    """Return the canonical evidence used by workbook and presentation builders."""

    return json_safe(
        {
            "metadata": service.metadata(),
            "data_quality": service.data_quality(),
            "kpis": service.kpis(),
            "root_cause": service.root_cause(),
            "strategy_comparison": service.strategy_comparison(),
            "partners": service.partners(),
            "vendors": service.vendors(),
            "memberships": service.memberships(),
            "scenarios": service.scenarios(),
            "baseline_scenario": service.scenario_run(
                {"scenario_name": "Baseline", "horizon_months": 12}
            ),
            "alerts": service.alerts(),
            "commentary": service.commentary(),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["evidence", "excel", "powerbi", "all"], default="all")
    parser.add_argument("--profile", choices=["test", "small", "default"], default="default")
    parser.add_argument("--data-root", type=Path, default=REPOSITORY_ROOT / "data")
    parser.add_argument(
        "--evidence-path",
        type=Path,
        default=REPOSITORY_ROOT / "exports" / "validation" / "evidence_snapshot.json",
    )
    args = parser.parse_args()
    service = WorkbenchService(load_config(args.profile, data_root=args.data_root))
    outputs: dict[str, object] = {}
    if args.format in {"evidence", "all"}:
        args.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_path.write_text(
            json.dumps(evidence_snapshot(service), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        outputs["evidence"] = str(args.evidence_path)
    if args.format in {"excel", "all"}:
        outputs["excel"] = service.export_excel()
    if args.format in {"powerbi", "all"}:
        outputs["powerbi"] = service.export_powerbi()
    print(json.dumps(json_safe(outputs), indent=2))


if __name__ == "__main__":
    main()
