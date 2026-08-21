from __future__ import annotations


def test_statistical_segmentation_is_reproducible_and_governed(service) -> None:
    first = service.segments()["statistical"]
    second = service.segments()["statistical"]

    assert first == second
    assert first["status"] == "implemented"
    assert first["selected_clusters"] in {3, 4, 5}
    assert len(first["clusters"]) == first["selected_clusters"]
    assert sum(cluster["accounts"] for cluster in first["clusters"]) == first["sample_size"]
    assert 0 <= first["silhouette_score"] <= 1
    assert 0 <= first["stability_adjusted_rand_index"] <= 1
    assert first["surrogate"]["depth"] <= 3
    assert 0 <= first["surrogate"]["accuracy"] <= 1
    assert first["governance"]["protected_attributes_used"] is False
    assert "Production customer-level credit decision" in first["governance"]["prohibited_use"]
