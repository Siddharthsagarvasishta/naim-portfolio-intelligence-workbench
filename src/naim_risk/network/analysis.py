"""Dependency centrality and node-removal impact without external graph libraries."""

from __future__ import annotations

from typing import Any

import pandas as pd

from naim_risk.common.math import hhi


def build_dependency_network(
    master: pd.DataFrame,
    benefit_usage: pd.DataFrame,
    service_incidents: pd.DataFrame,
) -> dict[str, Any]:
    account_edges = master[
        ["account_id", "product_type", "membership_tier_id", "partner_id", "vendor_id", "geography"]
    ]
    edge_rows = []
    for row in account_edges.itertuples(index=False):
        for source_type, source, target_type, target in [
            ("product", row.product_type, "partner", row.partner_id),
            ("product", row.product_type, "vendor", row.vendor_id),
            ("membership", row.membership_tier_id, "partner", row.partner_id),
            ("region", row.geography, "vendor", row.vendor_id),
        ]:
            edge_rows.append(
                {
                    "source": f"{source_type}:{source}",
                    "target": f"{target_type}:{target}",
                    "weight": 1.0,
                }
            )
    if len(benefit_usage):
        for row in benefit_usage[["benefit_id", "partner_id"]].itertuples(index=False):
            edge_rows.append(
                {
                    "source": f"benefit:{row.benefit_id}",
                    "target": f"partner:{row.partner_id}",
                    "weight": 1.0,
                }
            )
    edges = pd.DataFrame(edge_rows)
    grouped = edges.groupby(["source", "target"], as_index=False)["weight"].sum()
    degree: dict[str, set[str]] = {}
    weighted: dict[str, float] = {}
    for row in grouped.itertuples(index=False):
        degree.setdefault(row.source, set()).add(row.target)
        degree.setdefault(row.target, set()).add(row.source)
        weighted[row.source] = weighted.get(row.source, 0.0) + float(row.weight)
        weighted[row.target] = weighted.get(row.target, 0.0) + float(row.weight)
    nodes = []
    for node in sorted(degree):
        neighbour_weights = grouped.loc[
            (grouped["source"] == node) | (grouped["target"] == node), "weight"
        ]
        nodes.append(
            {
                "node_id": node,
                "node_type": node.split(":", 1)[0],
                "label": node.split(":", 1)[1],
                "degree_centrality": len(degree[node]) / max(len(degree) - 1, 1),
                "weighted_degree": weighted[node],
                "dependency_concentration": hhi(neighbour_weights),
                "single_point_of_failure_score": (
                    weighted[node] / max(sum(weighted.values()), 1) * 200
                ),
            }
        )
    return {
        "nodes": nodes,
        "edges": grouped.to_dict(orient="records"),
        "incident_count": int(len(service_incidents)),
        "methodology": "Degree and weighted-degree centrality on canonical cross-domain links; not causal.",
    }


def network_impact(
    node_id: str,
    master: pd.DataFrame,
    performance: pd.DataFrame,
) -> dict[str, Any]:
    node_type, value = node_id.split(":", 1)
    field_map = {
        "partner": "partner_id",
        "vendor": "vendor_id",
        "product": "product_type",
        "membership": "membership_tier_id",
        "region": "geography",
    }
    if node_type not in field_map:
        raise ValueError(f"Unsupported impact node type: {node_type}")
    affected_master = master[master[field_map[node_type]] == value]
    affected = performance[performance["account_id"].isin(affected_master["account_id"])]
    return {
        "removed_node": node_id,
        "affected_customers": int(affected_master["customer_id"].nunique()),
        "affected_accounts": int(affected_master["account_id"].nunique()),
        "affected_transaction_value": float(affected["transaction_value"].sum()),
        "affected_balance": float(affected["account_balance"].sum()),
        "affected_products": sorted(affected_master["product_type"].unique().tolist()),
        "affected_regions": sorted(affected_master["geography"].unique().tolist()),
        "scenario_notice": "Node-removal impact is a synthetic dependency scenario, not a forecast.",
    }
