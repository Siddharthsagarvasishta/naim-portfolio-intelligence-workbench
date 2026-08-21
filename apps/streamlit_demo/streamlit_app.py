"""Read-only Streamlit companion for the nAIM 60-second story."""

from __future__ import annotations

from typing import Any

import pandas as pd

from apps.streamlit_demo.app_core import find_sample_workbook, load_public_evidence

DISCLAIMER = (
    "Public demonstration only. All data, names, findings, thresholds and currency values are "
    "synthetic and institution-neutral. Outputs are not investment advice, credit decisions, "
    "regulatory stress-test results or causal claims. Human review is required."
)


def _pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def _render_unavailable(st: Any, detail: str) -> None:
    st.error("Public evidence is unavailable")
    st.caption(detail)
    st.info(
        "The application does not silently fall back to demo data. Select a validated offline "
        "snapshot or configure the governed public API endpoint."
    )


def _render_market_lab(st: Any, market: dict[str, Any]) -> None:
    st.subheader("Market Risk and Volatility Lab")
    if market.get("status") != "LIVE":
        st.warning("UNAVAILABLE — validation pending")
        st.caption(str(market.get("reason", "No approved public market-risk evidence snapshot.")))
        return
    summary = market["summary"]
    columns = st.columns(3)
    columns[0].metric("Historical volatility", _pct(summary["historical_volatility"]))
    columns[1].metric("EWMA forecast", _pct(summary["ewma_forecast_volatility"]))
    columns[2].metric(f"VaR ({summary['confidence']:.0%})", _pct(summary["historical_var"]))
    st.caption(
        f"Synthetic instrument: {market['instrument']} · {market['observation_count']:,} "
        "aggregate return observations. No trade signal is produced."
    )
    models = pd.DataFrame(market.get("model_comparison", []))
    if not models.empty:
        st.dataframe(models, use_container_width=True, hide_index=True)
    st.info(
        "VaR is a quantile estimate, not maximum possible loss. Results depend on sample period, "
        "price basis and modelling assumptions."
    )


def render_app(st: Any) -> None:
    """Render the public structure; dependency injection keeps smoke tests offline."""

    st.set_page_config(
        page_title="nAIM Portfolio Intelligence Workbench",
        page_icon="nAIM",
        layout="wide",
    )
    source = load_public_evidence()
    st.title("nAIM Portfolio Intelligence Workbench")
    st.caption(
        "Name the movement. Own the evidence. · nAIM is pronounced “name”. · AIM = All Is Mine."
    )
    st.sidebar.subheader("Evidence status")
    st.sidebar.metric("Data mode", source.mode)
    st.sidebar.metric("Health", source.health)
    st.sidebar.caption(source.source_label)
    st.sidebar.caption(source.detail)
    st.sidebar.warning(DISCLAIMER)

    if source.evidence is None:
        _render_unavailable(st, source.detail)
        return

    evidence = source.evidence
    story = evidence["portfolio_story"]
    decomposition = evidence["decomposition"]
    validation = evidence["validation"]

    st.success(
        f"{source.mode} · data-quality {validation['data_quality_status']} · "
        f"publication approved · evidence {evidence['evidence_id']}"
    )
    st.header("The 60-second story")
    columns = st.columns(4)
    columns[0].metric(
        "Annualised net loss rate",
        _pct(story["current_annualised_net_loss_rate"]),
        f"+{story['observed_change_bps']:.1f} bps",
        delta_color="inverse",
    )
    columns[1].metric("Prior month", _pct(story["prior_annualised_net_loss_rate"]))
    columns[2].metric("Mix contribution", f"+{decomposition['mix_bps']:.1f} bps")
    columns[3].metric("Within-segment", f"+{decomposition['within_segment_bps']:.1f} bps")

    st.markdown(
        f"""
1. **Name the movement.** In {story["reporting_period_label"]}, annualised net loss rate rose to
   **{_pct(story["current_annualised_net_loss_rate"])}**, a **+{story["observed_change_bps"]:.1f} bps** movement.
2. **Own the evidence.** The exact bridge reconciles **+{decomposition["mix_bps"]:.1f} bps** of mix and
   **+{decomposition["within_segment_bps"]:.1f} bps** of within-segment performance.
3. **Bound the claim.** **{decomposition["primary_driver"]}** is the largest acquisition-channel
   contributor, but the finding is **{decomposition["causal_status"].lower()}**, not causal.
4. **Govern the handoff.** Strategy output is **{evidence["strategy"]["decision"]}** and requires
   approval because the sample-ratio check failed.
"""
    )

    trend = pd.DataFrame(evidence["loss_rate_trend"])
    if not trend.empty:
        trend["month"] = pd.to_datetime(trend["month"])
        trend["annualised net loss rate"] = trend["value"] * 100
        st.subheader("Calculated annualised net loss rate (%)")
        st.line_chart(trend, x="month", y="annualised net loss rate")
        st.caption(
            "Aggregate monthly metric; annualisation is a presentation measure, not a forecast."
        )

    strategy_rows = pd.DataFrame(evidence["strategy"]["comparison"])
    if not strategy_rows.empty:
        st.subheader("Strategy trade-off")
        st.dataframe(strategy_rows, use_container_width=True, hide_index=True)
        st.caption(evidence["strategy"]["causal_warning"])

    _render_market_lab(st, evidence["market_risk"])

    st.header("Public artifact")
    workbook = find_sample_workbook()
    if workbook is None:
        st.info("Sample Excel download is pending final artifact validation.")
    else:
        st.download_button(
            "Download validated sample Excel workbook",
            data=workbook.read_bytes(),
            file_name=workbook.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    st.caption(
        "This companion is read-only: it has no administrative writes, configuration mutation, "
        "raw account view, credential entry or external model call."
    )
    st.warning(DISCLAIMER)


def main() -> None:
    import streamlit as st

    render_app(st)


if __name__ == "__main__":
    main()
