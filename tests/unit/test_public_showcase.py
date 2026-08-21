from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from apps.streamlit_demo import app_core, streamlit_app
from apps.streamlit_demo.app_core import PublicSourceResult
from scripts.build_share_site import (
    DEFAULT_SOURCE,
    build_public_evidence,
    build_share_site,
    validate_share_site,
)


class FakeStreamlit:
    def __init__(self) -> None:
        self.sidebar = self
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    def set_page_config(self, *args: Any, **kwargs: Any) -> None:
        self._record("set_page_config", *args, **kwargs)

    def title(self, *args: Any, **kwargs: Any) -> None:
        self._record("title", *args, **kwargs)

    def header(self, *args: Any, **kwargs: Any) -> None:
        self._record("header", *args, **kwargs)

    def subheader(self, *args: Any, **kwargs: Any) -> None:
        self._record("subheader", *args, **kwargs)

    def caption(self, *args: Any, **kwargs: Any) -> None:
        self._record("caption", *args, **kwargs)

    def metric(self, *args: Any, **kwargs: Any) -> None:
        self._record("metric", *args, **kwargs)

    def success(self, *args: Any, **kwargs: Any) -> None:
        self._record("success", *args, **kwargs)

    def warning(self, *args: Any, **kwargs: Any) -> None:
        self._record("warning", *args, **kwargs)

    def info(self, *args: Any, **kwargs: Any) -> None:
        self._record("info", *args, **kwargs)

    def error(self, *args: Any, **kwargs: Any) -> None:
        self._record("error", *args, **kwargs)

    def markdown(self, *args: Any, **kwargs: Any) -> None:
        self._record("markdown", *args, **kwargs)

    def line_chart(self, *args: Any, **kwargs: Any) -> None:
        self._record("line_chart", *args, **kwargs)

    def dataframe(self, *args: Any, **kwargs: Any) -> None:
        self._record("dataframe", *args, **kwargs)

    def download_button(self, *args: Any, **kwargs: Any) -> None:
        self._record("download_button", *args, **kwargs)

    def columns(self, count: int) -> list[FakeStreamlit]:
        self._record("columns", count)
        return [self for _ in range(count)]


@pytest.fixture
def public_evidence(tmp_path: Path) -> dict[str, Any]:
    return build_public_evidence(DEFAULT_SOURCE, tmp_path / "missing-market.json")


def test_public_evidence_is_reconciled_and_reduced(public_evidence: dict[str, Any]) -> None:
    story = public_evidence["portfolio_story"]
    bridge = public_evidence["decomposition"]
    assert story["observed_change_bps"] == pytest.approx(311.4150049234624)
    assert bridge["mix_bps"] + bridge["within_segment_bps"] + bridge[
        "residual_bps"
    ] == pytest.approx(story["observed_change_bps"])
    assert public_evidence["synthetic_data"] is True
    assert public_evidence["validation"]["publication_allowed"] is True
    assert len(public_evidence["kpi_snapshot"]) == 15
    assert public_evidence["source_context"]["dataset_hash"]
    assert public_evidence["source_context"]["configuration_hash"]
    assert public_evidence["market_risk"]["status"] == "UNAVAILABLE"
    serialized = json.dumps(public_evidence).lower()
    for forbidden in ("account_id", "customer_id", "password", "access_token", "/users/"):
        assert forbidden not in serialized


def test_static_site_build_is_backend_free_and_portable(tmp_path: Path) -> None:
    output = tmp_path / "share-site"
    streamlit_snapshot = tmp_path / "streamlit" / "evidence.json"
    manifest = build_share_site(
        source_path=DEFAULT_SOURCE,
        market_path=tmp_path / "missing-market.json",
        output=output,
        workbook=tmp_path / "missing.xlsx",
        streamlit_snapshot=streamlit_snapshot,
    )
    assert manifest["validation"]["status"] == "PASS"
    assert manifest["validation"]["backend_required"] is False
    assert manifest["sample_workbook_included"] is False
    assert manifest["market_risk_status"] == "UNAVAILABLE"
    assert manifest["artifact_type"] == "STATIC_SHARE_PACKAGE"
    assert manifest["validation_status"] == "PASS"
    assert validate_share_site(output)["status"] == "PASS"
    page = (output / "index.html").read_text(encoding="utf-8")
    for required in (
        "PROJECT OVERVIEW",
        "ARCHITECTURE",
        "THE 60-SECOND STORY",
        "PRODUCT PREVIEWS",
        "METHODOLOGY",
        "MARKET RISK &amp; VOLATILITY LAB",
        "PUBLIC DOWNLOADS",
        "TECHNOLOGY STACK",
        "LIMITATIONS",
        "Synthetic-data statement",
        "Repository link — configure at build time",
        "Contact — configure at build time",
    ):
        assert required in page
    assert "http://localhost" not in page
    assert streamlit_snapshot.is_file()
    assert streamlit_snapshot.with_suffix(".json.sha256").is_file()


def test_validated_market_snapshot_is_reduced_to_aggregate_evidence(tmp_path: Path) -> None:
    market_path = tmp_path / "market.json"
    market_path.write_text(
        json.dumps(
            {
                "status": "implemented",
                "validation": {"status": "PASS", "publication_allowed": True},
                "source": {
                    "instrument": "NAIM-DEMO-INDEX",
                    "provider": "bundled_deterministic_sample",
                    "source_is_synthetic": True,
                    "redistribution_permitted": True,
                },
                "returns": {"summary": {"observations": 500}},
                "historical_volatility": {
                    "estimators": {"close_to_close": {"annualised_volatility": 0.184}}
                },
                "ewma": {"one_step_annualised_volatility_forecast": 0.196},
                "var_expected_shortfall": {
                    "confidence": 0.99,
                    "methods": {"historical": {"var": 0.027, "expected_shortfall": 0.036}},
                },
                "model_comparison": {
                    "models": [
                        {
                            "model": "ewma",
                            "one_step_forecast": 0.196,
                            "out_of_sample_qlike": -7.2,
                            "diagnostic_status": "non_parametric",
                        }
                    ]
                },
                "governance": {
                    "trading_recommendation": False,
                    "causal_claim": False,
                    "limitations": ["Synthetic educational sample."],
                },
            }
        ),
        encoding="utf-8",
    )
    evidence = build_public_evidence(DEFAULT_SOURCE, market_path)
    market = evidence["market_risk"]
    assert market["status"] == "LIVE"
    assert market["observation_count"] == 500
    assert market["summary"]["historical_var"] == pytest.approx(0.027)
    serialized = json.dumps(market)
    assert 'observations"' not in serialized
    assert "prices" not in serialized


def test_offline_loader_verifies_checksum(tmp_path: Path, public_evidence: dict[str, Any]) -> None:
    snapshot = tmp_path / "evidence.json"
    snapshot.write_text(json.dumps(public_evidence, sort_keys=True), encoding="utf-8")
    digest = app_core.hashlib.sha256(snapshot.read_bytes()).hexdigest()
    snapshot.with_suffix(".json.sha256").write_text(f"{digest}  evidence.json\n", encoding="utf-8")
    loaded = app_core.load_public_evidence(source_mode="OFFLINE_SNAPSHOT", snapshot_path=snapshot)
    assert loaded.health == "PASS"
    assert loaded.mode == "OFFLINE_SNAPSHOT"
    snapshot.write_text("{}", encoding="utf-8")
    rejected = app_core.load_public_evidence(source_mode="OFFLINE_SNAPSHOT", snapshot_path=snapshot)
    assert rejected.mode == "UNAVAILABLE"
    assert "checksum" in rejected.detail.lower()


def test_api_mode_never_falls_back_to_snapshot(tmp_path: Path) -> None:
    result = app_core.load_public_evidence(
        source_mode="API",
        snapshot_path=tmp_path / "would-be-fallback.json",
        api_base_url=None,
    )
    assert result.evidence is None
    assert result.mode == "UNAVAILABLE"
    assert "NAIM_PUBLIC_API_BASE_URL" in result.detail


def test_streamlit_structure_renders_without_backend(
    monkeypatch: pytest.MonkeyPatch,
    public_evidence: dict[str, Any],
) -> None:
    fake = FakeStreamlit()
    monkeypatch.setattr(
        streamlit_app,
        "load_public_evidence",
        lambda: PublicSourceResult(
            public_evidence,
            "OFFLINE_SNAPSHOT",
            "PASS",
            "Validated test evidence.",
            "validated offline evidence snapshot",
        ),
    )
    monkeypatch.setattr(streamlit_app, "find_sample_workbook", lambda: None)
    streamlit_app.render_app(fake)
    names = [call[0] for call in fake.calls]
    assert "title" in names
    assert "line_chart" in names
    assert "dataframe" in names
    assert "warning" in names
    assert "download_button" not in names
    text = " ".join(str(arg) for _, args, _ in fake.calls for arg in args)
    assert "UNAVAILABLE — validation pending" in text
    assert "synthetic" in text.lower()


def test_streamlit_sample_workbook_download_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    public_evidence: dict[str, Any],
) -> None:
    workbook = tmp_path / "nAIM_Portfolio_Intelligence_Workbench.xlsx"
    workbook.write_bytes(b"validated-sample")
    fake = FakeStreamlit()
    monkeypatch.setattr(
        streamlit_app,
        "load_public_evidence",
        lambda: PublicSourceResult(
            public_evidence,
            "OFFLINE_SNAPSHOT",
            "PASS",
            "Validated test evidence.",
            "validated offline evidence snapshot",
        ),
    )
    monkeypatch.setattr(streamlit_app, "find_sample_workbook", lambda: workbook)
    streamlit_app.render_app(fake)
    downloads = [call for call in fake.calls if call[0] == "download_button"]
    assert len(downloads) == 1
    assert downloads[0][2]["data"] == b"validated-sample"


def test_linkedin_copy_reconciles_and_discloses_synthetic_data() -> None:
    root = Path(__file__).resolve().parents[2] / "outputs" / "linkedin"
    if not root.is_dir():
        pytest.skip("LinkedIn release package has not been generated in this checkout")
    summary = (root / "project-summary.md").read_text(encoding="utf-8")
    research = (root / "research-summary.md").read_text(encoding="utf-8")
    combined = summary + research
    for expected in ("311.4", "4.4", "307.0", "6.69%", "3.57%", "89.75%"):
        assert expected in combined
    assert "synthetic" in combined.lower()
    manifest = json.loads((root / "package-manifest.json").read_text(encoding="utf-8"))
    assert manifest["automatic_linkedin_posting"] is False
    assert manifest["market_risk_public_result"] == "LIVE_VALIDATED_SYNTHETIC"
