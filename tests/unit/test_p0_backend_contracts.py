from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from naim_risk.alerts import build_alert_candidate
from naim_risk.config import metric_display_contract, metric_lookup
from naim_risk.runtime_modes import DataMode, SourceContext
from naim_risk.service import WorkbenchService
from naim_risk.workflow import WorkflowStore


def _sqlite_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.resolve()}"


@pytest.mark.parametrize(
    ("unit", "scale", "scaling_factor", "format_string"),
    [
        ("accounts", "whole_count", 1.0, "#,##0"),
        ("annualised_rate", "fraction", 100.0, "0.00%"),
        ("basis_points", "basis_points", 1.0, '#,##0.0 "bps"'),
        ("currency", "adaptive_currency", 1.0, "$0.0a;[Red]($0.0a)"),
        ("per_1000", "per_1000_accounts", 1.0, '#,##0.0 "per 1,000"'),
        ("rate", "fraction", 100.0, "0.00%"),
    ],
)
def test_all_current_raw_units_have_one_governed_display_contract(
    unit: str,
    scale: str,
    scaling_factor: float,
    format_string: str,
) -> None:
    contract = metric_display_contract({"unit": unit})
    assert contract["unit"] == unit
    assert contract["scale"] == scale
    assert contract["scaling_factor"] == scaling_factor
    assert contract["format_string"] == format_string


def test_currency_display_contract_is_explicitly_adaptive_usd() -> None:
    contract = metric_display_contract({"unit": "currency"})
    assert contract == {
        "unit": "currency",
        "scale": "adaptive_currency",
        "scaling_factor": 1.0,
        "format_string": "$0.0a;[Red]($0.0a)",
        "currency_code": "USD",
        "currency_symbol": "$",
    }


def test_every_core_kpi_and_contribution_member_exposes_governed_contract(service) -> None:
    registry = metric_lookup(service.config)
    kpis = service.kpis()["data"]
    required = {
        "unit",
        "scale",
        "numerator",
        "denominator",
        "scaling_factor",
        "format_string",
    }
    assert kpis
    for row in kpis:
        assert required <= row.keys()
        assert isinstance(row["denominator"], (int, float))
        if row["metric_id"] in registry:
            governed = metric_display_contract(registry[row["metric_id"]])
            assert row["unit"] == governed["unit"]
            assert row["scale"] == governed["scale"]
            assert row["scaling_factor"] == governed["scaling_factor"]
            assert row["format_string"] == governed["format_string"]
            assert row["numerator"] == registry[row["metric_id"]]["numerator"]

    root = service.root_cause()
    assert root["lenses"]
    for lens in root["lenses"]:
        for member in lens["segments"]:
            assert member["dimension"] == lens["dimension"]


@pytest.mark.parametrize("mode", [DataMode.DEMO, DataMode.OFFLINE_SNAPSHOT])
def test_instant_demo_is_idempotent_and_preserves_governed_scope_and_evidence(
    mode: DataMode,
    tmp_path: Path,
    test_config,
    pipeline_data,
) -> None:
    store = WorkflowStore(_sqlite_url(tmp_path / f"demo-{mode.value}.sqlite3"))
    workbench = WorkbenchService(test_config, pipeline_data, workflow_store=store)
    context = SourceContext(
        active_mode=mode,
        configured_mode=mode,
        snapshot_date=str(workbench.data.manifest.get("maximum_data_date")),
        configuration_hash=test_config.config_hash,
        dataset_hash=sha256(workbench.data.run_id.encode()).hexdigest(),
        dataset_hash_basis="pipeline-run-id",
        run_id=workbench.data.run_id,
        synthetic=True,
        reason=None,
    )

    first = workbench.run_demo(actor="portfolio.analyst", source_context=context)
    second = workbench.run_demo(actor="portfolio.analyst", source_context=context)

    assert first["reused"] is False
    assert second["reused"] is True
    assert first["demo_run_id"] == second["demo_run_id"]
    assert first["active_mode"] == mode.value
    assert first["workspace"]["workspace_id"] == second["workspace"]["workspace_id"]
    assert first["workspace"]["approved_flag"] is True
    assert first["investigation"]["investigation_id"] == second["investigation"][
        "investigation_id"
    ]
    assert first["commentary"]["commentary_id"] == second["commentary"][
        "commentary_id"
    ]
    assert first["scope"]["reporting_period"]
    assert first["scope"]["comparison_period"]
    assert first["scope"]["filters"] == {}
    authoritative_root = workbench.root_cause(
        period=first["scope"]["reporting_period"]
    )["finding"]
    demo_root = first["evidence"]["root_cause"]["finding"]
    assert demo_root["observed_change_bps"] == pytest.approx(
        authoritative_root["observed_change_bps"]
    )
    assert demo_root["primary_dimension"] == authoritative_root["primary_dimension"]
    assert demo_root["primary_driver"] == authoritative_root["primary_driver"]
    assert first["data_quality"]["publication_allowed"] is True
    assert set(first["story"]) >= {
        "what_changed",
        "why",
        "uncertainties",
        "supported_action",
        "evidence_produced",
        "outputs_available",
    }
    assert set(first["evidence"]) >= {
        "evidence_id",
        "command_centre",
        "root_cause",
        "vintages",
        "strategy_comparison",
        "alerts",
        "scenario",
    }
    assert [step["step_id"] for step in first["steps"]] == list(range(1, 16))
    demo_alerts = first["evidence"]["alerts"]["data"]
    assert first["evidence"]["alerts"]["metadata"]["alert_workflow_scope"] in {
        "current_durable_workflow",
        "approved_demo_historical_durable_workflow",
    }
    assert all(alert["workflow_active"] is True for alert in demo_alerts)
    assert all(alert["audit_integrity"]["status"] == "PASS" for alert in demo_alerts)
    expected_alert_scope = {
        key: [value] if isinstance(value, str) else value
        for key, value in first["scope"]["filters"].items()
    }
    assert all(alert["selected_scope"] == expected_alert_scope for alert in demo_alerts)
    assert [alert["alert_id"] for alert in demo_alerts] == [
        alert["alert_id"] for alert in second["evidence"]["alerts"]["data"]
    ]
    assert workbench.demo_status(first["demo_run_id"])["reused"] is True

    demo_workspaces = [
        row
        for row in store.list("workspace")
        if row["state"].get("record_kind") == "demo_workspace"
    ]
    demo_investigations = [
        row
        for row in store.list("investigation")
        if row["state"].get("record_kind") == "demo_investigation"
    ]
    demo_runs = [
        row
        for row in store.list("configuration_change")
        if row["state"].get("record_kind") == "demo_run"
    ]
    assert len(demo_workspaces) == len(demo_investigations) == len(demo_runs) == 1
    assert len(store.list("commentary")) == 1
    assert len(store.list("alert")) == len(demo_alerts)
    store.close()


def test_reused_demo_refreshes_current_durable_alert_lifecycle(
    tmp_path: Path,
    test_config,
    pipeline_data,
) -> None:
    store = WorkflowStore(_sqlite_url(tmp_path / "demo-lifecycle.sqlite3"))
    workbench = WorkbenchService(test_config, pipeline_data, workflow_store=store)
    context = SourceContext(
        active_mode=DataMode.DEMO,
        configured_mode=DataMode.DEMO,
        snapshot_date=str(workbench.data.manifest.get("maximum_data_date")),
        configuration_hash=test_config.config_hash,
        dataset_hash=sha256(workbench.data.run_id.encode()).hexdigest(),
        dataset_hash_basis="pipeline-run-id",
        run_id=workbench.data.run_id,
        synthetic=True,
        reason=None,
    )
    first = workbench.run_demo(actor="portfolio.analyst", source_context=context)
    selected_scope = {"product_type": ["Card"]}
    candidate = build_alert_candidate(
        {
            "alert_rule_id": "LOSS_MOVEMENT",
            "metric_id": "ANNUALISED_NET_LOSS_RATE",
            "alert_name": "Loss rate increased materially",
            "comparison_method": "basis_point_movement",
            "relative_threshold": 20,
            "minimum_denominator": 100,
            "consecutive_periods": 1,
            "severity": "Adverse",
            "cooldown_period": 1,
            "sla_hours": 24,
            "owner_role": "Portfolio Risk Analytics",
            "recommended_investigation": "Review the reconciled loss movement.",
        },
        current_value=0.08,
        baseline_value=0.07,
        denominator=1_000,
        period="2025-08-01",
        comparison_period="2025-07-01",
        quality_status="PASS",
        selected_scope=selected_scope,
        rule_version="2.0.0",
    )
    created = workbench.alert_lifecycle.reconcile(
        [candidate],
        run_id=workbench.data.run_id,
        configuration_hash=test_config.config_hash,
        dataset_hash=context.dataset_hash,
        evaluation_period="2025-08-01",
        selected_scope=selected_scope,
    )[0]
    demo_record = store.get("configuration_change", first["demo_run_id"])
    demo_state = dict(demo_record["state"])
    demo_evidence = dict(demo_state["evidence"])
    demo_evidence["alerts"] = {
        "data": [created],
        "metadata": {"alert_workflow_scope": "approved_demo_historical_durable_workflow"},
    }
    demo_state["evidence"] = demo_evidence
    store.update(
        "configuration_change",
        first["demo_run_id"],
        demo_state,
        expected_version=int(demo_record["version"]),
        actor="test.setup",
        replace=True,
    )
    investigated = workbench.alert_lifecycle.transition(
        created["alert_id"],
        expected_version=created["version"],
        target_status="INVESTIGATING",
        reason="Validate durable portfolio-story persistence.",
        actor="portfolio.analyst",
        related_investigation="INV-PERSISTENCE",
        selected_scope=selected_scope,
    )

    refreshed = workbench.run_demo(actor="portfolio.analyst", source_context=context)
    refreshed_alert = refreshed["evidence"]["alerts"]["data"][0]
    assert refreshed["reused"] is True
    assert refreshed_alert["status"] == "INVESTIGATING"
    assert refreshed_alert["version"] == investigated["version"]
    assert refreshed_alert["related_investigation"] == "INV-PERSISTENCE"
    assert refreshed["steps"][10]["result"]["data"][0] == refreshed_alert
    assert workbench.demo_status(first["demo_run_id"])["evidence"]["alerts"][
        "data"
    ][0] == refreshed_alert
    store.close()
