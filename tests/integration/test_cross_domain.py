from __future__ import annotations

import pytest


@pytest.mark.integration
def test_partner_vendor_membership_reconcile(service):
    partners = service.partners()
    assert partners["summary"]["active_partners"] == 6
    assert partners["summary"]["transaction_concentration_hhi"] > 0
    assert all(row["contract_version"] == "1.0" for row in partners["data"])
    vendors = service.vendors()
    assert vendors["summary"]["active_vendors"] == 6
    assert vendors["summary"]["total_vendor_cost"] == pytest.approx(
        sum(row["total_vendor_cost"] for row in vendors["data"])
    )
    memberships = service.memberships()
    assert memberships["summary"]["active_members"] == sum(
        row["active_members"] for row in memberships["data"]
    )
    transitions = service.membership_transitions()
    assert transitions["upgrades"] + transitions["downgrades"] > 0


@pytest.mark.integration
def test_network_capacity_and_basket_operations_are_live(service):
    network = service.network()
    assert network["nodes"]
    partner_node = next(
        node["node_id"] for node in network["nodes"] if node["node_type"] == "partner"
    )
    impact = service.network_impact(partner_node)
    assert impact["affected_accounts"] > 0
    capacity = service.capacity_scenario({"volume_multiplier": 1.25, "capacity_multiplier": 0.8})
    assert capacity["data"]
    combined = service.combine_baskets(
        {
            "left_members": ["PARTNER-01", "PARTNER-02"],
            "right_members": ["PARTNER-02", "PARTNER-03"],
            "operation": "union",
        }
    )
    assert combined["members"] == ["PARTNER-01", "PARTNER-02", "PARTNER-03"]


@pytest.mark.integration
def test_finance_bridge_has_reconciling_opening_and_closing_totals(service):
    finance = service.finance()
    bridge = finance["bridge"]

    assert bridge[0]["group"] == "opening"
    assert bridge[-1]["group"] == "closing"
    effects = bridge[1:-1]
    assert bridge[0]["value"] + sum(row["value"] for row in effects) == pytest.approx(
        bridge[-1]["value"]
    )
    assert finance["bridge_reconciliation"]["reconciled"] is True
    assert finance["bridge_reconciliation"]["residual"] == pytest.approx(0, abs=1e-8)
