from __future__ import annotations

from pathlib import Path

import pytest

from naim_risk.workflow import ConcurrencyConflict, ObjectNotFound, WorkflowStore


def sqlite_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.resolve()}"


def test_workflow_objects_survive_store_restart(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"
    store = WorkflowStore(sqlite_url(database))
    required_types = {
        "investigation": "INV-000001",
        "investigation_note": "NOTE-000001",
        "basket": "BASKET-000001",
        "basket_membership": "BASKET-MEMBERS-000001",
        "workspace": "WORKSPACE-000001",
        "workspace_version": "WORKSPACE-VERSION-000001",
        "approval": "APPROVAL-000001",
        "commentary": "COMMENTARY-000001",
        "export_job": "EXPORT-000001",
        "scenario_run": "SCENARIO-000001",
        "rating_methodology": "RATING-000001",
        "configuration_change": "CONFIG-000001",
    }
    for object_type, external_id in required_types.items():
        store.create(
            object_type,
            external_id,
            {"name": external_id, "owner": "analyst"},
            actor="portfolio.analyst",
        )
    store.close()

    restarted = WorkflowStore(sqlite_url(database))
    for object_type, external_id in required_types.items():
        restored = restarted.get(object_type, external_id)
        assert restored["external_id"] == external_id
        assert restored["version"] == 1
    restarted.close()


def test_optimistic_concurrency_history_approval_and_audit_chain(tmp_path: Path) -> None:
    store = WorkflowStore(sqlite_url(tmp_path / "state.sqlite3"))
    created = store.create(
        "investigation",
        "INV-000001",
        {"status": "NEW", "owner": "analyst"},
        actor="portfolio.analyst",
    )
    assert created["version"] == 1

    updated = store.update(
        "investigation",
        "INV-000001",
        {"status": "UNDER_REVIEW"},
        expected_version=1,
        actor="portfolio.analyst",
    )
    assert updated["version"] == 2
    assert updated["state"]["owner"] == "analyst"

    with pytest.raises(ConcurrencyConflict):
        store.update(
            "investigation",
            "INV-000001",
            {"status": "STALE_UPDATE"},
            expected_version=1,
            actor="other.analyst",
        )

    approved = store.set_approval(
        "investigation",
        "INV-000001",
        "APPROVED",
        expected_version=2,
        actor="administrator",
        rationale="Evidence reconciled and independently reviewed.",
    )
    assert approved["version"] == 3
    assert approved["approval_state"] == "APPROVED"
    assert [row["version"] for row in store.history("investigation", "INV-000001")] == [
        1,
        2,
        3,
    ]
    assert store.verify_audit_chain("investigation", "INV-000001")


def test_soft_delete_is_versioned_and_hidden_by_default(tmp_path: Path) -> None:
    store = WorkflowStore(sqlite_url(tmp_path / "state.sqlite3"))
    store.create(
        "workspace",
        "WORKSPACE-000001",
        {"name": "Review"},
        actor="portfolio.analyst",
    )
    deleted = store.soft_delete(
        "workspace",
        "WORKSPACE-000001",
        expected_version=1,
        actor="administrator",
        reason="Superseded by governed workspace version.",
    )
    assert deleted["version"] == 2
    assert deleted["deleted_at"] is not None
    assert store.list("workspace") == []
    with pytest.raises(ObjectNotFound):
        store.get("workspace", "WORKSPACE-000001")
    assert store.get("workspace", "WORKSPACE-000001", include_deleted=True)["state"][
        "deletion_reason"
    ]
    assert store.verify_audit_chain("workspace", "WORKSPACE-000001")


def test_validation_rejects_unknown_types_and_approval_states(tmp_path: Path) -> None:
    store = WorkflowStore(sqlite_url(tmp_path / "state.sqlite3"))
    with pytest.raises(ValueError, match="Unsupported workflow object type"):
        store.create("unknown", "X", {}, actor="administrator")
    with pytest.raises(ValueError, match="Unsupported approval state"):
        store.create(
            "investigation",
            "INV-1",
            {},
            actor="administrator",
            approval_state="AUTO_APPROVED",
        )
