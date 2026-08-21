from __future__ import annotations

import json
from pathlib import Path

import tableauhyperapi as hyper

from naim_risk.config import load_config
from naim_risk.service import WorkbenchService
from naim_risk.tableau import (
    DisabledTableauPublisher,
    PublishTarget,
    generate_hyper_extract,
)


def test_real_hyper_extract_reopens_and_reconciles_control_totals(tmp_path: Path) -> None:
    service = WorkbenchService(load_config("test", data_root=tmp_path / "data"))
    path = tmp_path / "nAIM_Portfolio_Intelligence.hyper"
    result = generate_hyper_extract(service, output_path=path)
    assert result["status"] == "PASS"
    assert result["filename"] == path.name
    assert "path" not in result
    assert result["publishing"]["published"] is False
    assert result["artifact_type"] == "TABLEAU_HYPER_EXTRACT"
    assert result["validation_status"] == "PASS"
    assert result["dataset_hash"]
    assert result["configuration_hash"] == service.config.config_hash
    assert result["tables"]
    assert all(row["expected_rows"] == row["actual_rows"] for row in result["tables"])

    with hyper.HyperProcess(hyper.Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as process:
        with hyper.Connection(process.endpoint, path) as connection:
            metadata_rows = list(
                connection.execute_list_query(
                    'SELECT "metadata_key", "metadata_value" FROM "Extract"."Metadata"'
                )
            )
            assert ["synthetic_data", "true"] in [list(row) for row in metadata_rows]
            assert connection.execute_scalar_query(
                'SELECT COUNT(*) FROM "Extract"."MetricVersion"'
            ) == len(service.config.metrics)

    manifest = json.loads(path.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert manifest["sha256"] == result["sha256"]
    assert manifest["configuration_hash"] == service.config.config_hash


def test_default_tableau_publisher_never_transmits(tmp_path: Path) -> None:
    result = DisabledTableauPublisher().publish(
        tmp_path / "extract.hyper",
        PublishTarget("https://tableau.invalid", "site", "project", "source"),
    )
    assert result.status == "DISABLED"
    assert result.published is False
    assert result.remote_identifier is None
