from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import naim_risk.service as service_module
from naim_risk.service import WorkbenchService
from naim_risk.workflow import ConcurrencyConflict, WorkflowStore


def sqlite_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.resolve()}"


@pytest.mark.integration
def test_service_workflows_survive_restart(
    tmp_path: Path,
    test_config,
    pipeline_data,
) -> None:
    database_url = sqlite_url(tmp_path / "workflows.sqlite3")
    first_store = WorkflowStore(database_url)
    first = WorkbenchService(test_config, pipeline_data, workflow_store=first_store)

    investigation = first.create_investigation(
        {"business_question": "Why did governed loss move?"},
        actor="portfolio.analyst",
    )
    basket = first.create_basket(
        {
            "basket_name": "Restart-safe accounts",
            "basket_description": "Durable synthetic test basket",
            "members": ["ACCOUNT-002", "ACCOUNT-001", "ACCOUNT-001"],
        },
        actor="portfolio.analyst",
    )
    workspace = first.create_workspace(
        {
            "workspace_name": "Restart-safe workspace",
            "business_question": "What changed in the governed portfolio?",
            "selected_metrics": ["ANNUALISED_NET_LOSS_RATE"],
        },
        actor="portfolio.analyst",
    )
    commentary = first.commentary({}, actor="portfolio.analyst")
    scenario = first.scenario_run(
        {"scenario_name": "Fraud Shock", "horizon_months": 2},
        actor="portfolio.analyst",
    )
    analysis = first.run_analysis_template(
        "MONTHLY_KPI_MOVEMENT",
        {},
        actor="portfolio.analyst",
    )
    export = first.export_powerbi(actor="portfolio.analyst")
    demo = first.run_demo(actor="portfolio.analyst")
    first_store.close()

    restarted_store = WorkflowStore(database_url)
    restarted = WorkbenchService(
        test_config,
        pipeline_data,
        workflow_store=restarted_store,
    )

    investigations = restarted.investigations()["data"]
    assert investigation["investigation_id"] in {row["investigation_id"] for row in investigations}
    restored_basket = restarted.basket_detail(basket["basket_id"])
    assert restored_basket["members"] == ["ACCOUNT-001", "ACCOUNT-002"]
    assert restored_basket["version"] == 1
    membership = restarted_store.get(
        "basket_membership",
        f"{basket['basket_id']}:members",
    )
    assert membership["state"]["basket_version"] == 1
    assert restarted.workspace_detail(workspace["workspace_id"])["version"] == 1
    assert restarted.commentary_record(commentary["commentary_id"])["version"] == 1
    assert restarted.scenario_run_record(scenario["run_id"])["version"] == 1
    assert restarted.analysis_run(analysis["run_id"])["template_id"] == ("MONTHLY_KPI_MOVEMENT")
    assert export["artifact_id"] in {row["artifact_id"] for row in restarted.exports()["data"]}
    assert restarted.resolve_export_artifact(export["artifact_id"]).is_file()
    export_state = restarted_store.get("export_job", export["artifact_id"])["state"]
    assert Path(export_state["filename"]).name == export_state["filename"]
    assert export_state["status"] == "completed"
    assert export_state["file_sha256"]
    assert export_state["created_at"]
    assert export_state["completed_at"]
    assert export_state["expires_at"]
    assert export_state["download_count"] == 0
    assert "path" not in export_state
    assert not any(
        isinstance(value, str) and value.startswith("/") for value in export_state.values()
    )
    assert restarted.demo_status(demo["run_id"])["status"] == "completed"

    after_restart = restarted.create_investigation(
        {"business_question": "Does a new identifier collide?"},
        actor="portfolio.analyst",
    )
    assert after_restart["investigation_id"] != investigation["investigation_id"]
    restarted_store.soft_delete(
        "investigation",
        after_restart["investigation_id"],
        expected_version=1,
        actor="administrator",
        reason="Exercise identifier allocation after deletion.",
    )
    after_delete = restarted.create_investigation(
        {"business_question": "Is deletion-safe allocation unique?"},
        actor="portfolio.analyst",
    )
    assert after_delete["investigation_id"] not in {
        investigation["investigation_id"],
        after_restart["investigation_id"],
    }
    restarted_store.close()


@pytest.mark.integration
def test_registered_export_rejects_tampered_file(
    tmp_path: Path,
    test_config,
    pipeline_data,
) -> None:
    database_url = sqlite_url(tmp_path / "workflows.sqlite3")
    store = WorkflowStore(database_url)
    service = WorkbenchService(test_config, pipeline_data, workflow_store=store)
    export = service.export_powerbi(actor="portfolio.analyst")
    state = store.get("export_job", export["artifact_id"])["state"]
    artifact = test_config.data_root / "generated_exports" / state["filename"]

    artifact.write_bytes(artifact.read_bytes() + b"tampered")

    with pytest.raises(KeyError):
        service.resolve_export_artifact(
            export["artifact_id"],
            actor="portfolio.analyst",
        )
    failed = store.get("export_job", export["artifact_id"])
    assert failed["state"]["status"] == "integrity_failed"
    assert "SHA-256" in failed["state"]["error"]
    assert failed["state"]["integrity_checked_at"]
    assert store.verify_audit_chain("export_job", export["artifact_id"])
    assert store.audit_events("export_job", export["artifact_id"])[-1]["event_hash"]
    store.close()


@pytest.mark.integration
def test_service_updates_reject_stale_versions(
    tmp_path: Path,
    test_config,
    pipeline_data,
) -> None:
    store = WorkflowStore(sqlite_url(tmp_path / "workflows.sqlite3"))
    service = WorkbenchService(test_config, pipeline_data, workflow_store=store)

    basket = service.create_basket(
        {"basket_name": "Concurrency basket", "members": ["ACCOUNT-001"]}
    )
    service.update_basket(
        basket["basket_id"],
        {"basket_description": "Current write"},
        expected_version=1,
    )
    with pytest.raises(ConcurrencyConflict):
        service.update_basket(
            basket["basket_id"],
            {"basket_description": "Stale write"},
            expected_version=1,
        )

    workspace = service.create_workspace(
        {
            "workspace_name": "Concurrency workspace",
            "business_question": "Which write wins?",
        }
    )
    service.update_workspace(
        workspace["workspace_id"],
        {"owner": "Current owner", "expected_version": 1},
    )
    with pytest.raises(ConcurrencyConflict):
        service.update_workspace(
            workspace["workspace_id"],
            {"owner": "Stale owner", "expected_version": 1},
        )

    investigation = service.create_investigation({"business_question": "Which evidence changed?"})
    service.update_investigation(
        investigation["investigation_id"],
        {"owner": "Current reviewer"},
        expected_version=1,
    )
    with pytest.raises(ConcurrencyConflict):
        service.update_investigation(
            investigation["investigation_id"],
            {"owner": "Stale reviewer"},
            expected_version=1,
        )
    store.close()


def test_fresh_pipeline_persists_outside_test_profile(
    monkeypatch,
    tmp_path: Path,
    test_config,
    pipeline_data,
) -> None:
    persist_values: list[bool] = []

    def fake_run_pipeline(config, *, persist):
        persist_values.append(persist)
        return pipeline_data

    monkeypatch.setattr(service_module, "run_pipeline", fake_run_pipeline)
    default_profile = replace(test_config.profile, name="default")
    default_config = replace(
        test_config,
        profile=default_profile,
        data_root=tmp_path / "default-data",
    )
    default_store = WorkflowStore(sqlite_url(tmp_path / "default.sqlite3"))
    WorkbenchService(default_config, workflow_store=default_store)
    default_store.close()

    test_store = WorkflowStore(sqlite_url(tmp_path / "test.sqlite3"))
    WorkbenchService(test_config, workflow_store=test_store)
    test_store.close()

    assert persist_values == [True, False]
