"use client";

import { useMemo, useReducer, useState } from "react";
import {
  acknowledgeDurableAlert,
  createAndLinkAlertInvestigation,
  createInvestigation,
  generateExecutivePack,
  generateExport,
  GovernedWorkflowError,
  transitionDurableAlert,
} from "../data/api-client";
import {
  activeAlertQueue,
  ALERT_TRANSITION_LABELS,
  alertHistory,
  alertMutationReducer,
  lifecycleStatusLabel,
} from "../data/alert-lifecycle";
import { formatMetricValue } from "../data/metric-format";
import {
  buildMetricEvidence,
  metricLineageAvailable,
} from "../data/governed-evidence";
import {
  earlyWarningHeadline,
  resolveContributionLens,
} from "../data/p0-contract";
import type {
  AlertLifecycleTransition,
  AlertRecord,
  EvidenceItem,
  ExecutivePackResult,
  InvestigationRecord,
  KpiMetric,
  PageProps,
  ViewKey,
} from "../workbench-types";
import {
  CohortCurves,
  ChartInteractionFrame,
  ContributionBars,
  formatCompact,
  HorizontalBars,
  QuadrantChart,
  RollRateMatrix,
  StrategyComparison,
  TrendBars,
  VintageHeatmap,
  WaterfallChart,
} from "./charts";
import {
  AnalystOnly,
  DataState,
  MethodologyPopover,
  MetricCard,
  ModeNote,
  PageHeader,
  Panel,
  SegmentedControl,
  SourceFooter,
  StatusChip,
  TableShell,
} from "./ui";
import {
  AdvancedStatisticsPage,
  MarketRiskPage,
} from "./quant-pages";

function metric(data: PageProps["data"], id: string): KpiMetric {
  return data.kpis.find((item) => item.id === id) ?? data.kpis[0];
}

function trendValues(data: PageProps["data"], id: string): number[] {
  return (
    data.trends
      .find((series) => series.id === id)
      ?.points.slice(-10)
      .map((point) => point.value) ?? []
  );
}

function isApiBacked(data: PageProps["data"]): boolean {
  return (
    data.metadata.dataMode === "LIVE" ||
    data.metadata.dataMode === "OFFLINE_SNAPSHOT"
  );
}

function numberFromDisplay(value: string | undefined): number | null {
  const match = value?.replaceAll(",", "").match(/-?\d+(?:\.\d+)?/);
  if (!match) return null;
  const parsed = Number(match[0]);
  return Number.isFinite(parsed) ? parsed : null;
}

type PackAttempt =
  | { phase: "idle" }
  | { phase: "working"; stage: string }
  | { phase: "ready"; pack: ExecutivePackResult }
  | { phase: "error"; stage: string; message: string };

function stageLabel(stage: string): string {
  return stage.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function ExecutivePackAction({
  props,
}: {
  props: PageProps;
}) {
  const { data, filters, portfolioStory } = props;
  const [attempt, setAttempt] = useState<PackAttempt>({ phase: "idle" });
  const unavailable = data.metadata.dataMode === "UNAVAILABLE";
  const request = async () => {
    setAttempt({ phase: "working", stage: "validating_scope" });
    try {
      const filterScope = Object.fromEntries(
        Object.entries(filters).filter(
          ([key, value]) =>
            key !== "reportingMonth" &&
            key !== "comparison" &&
            Boolean(value) &&
            !value.startsWith("All "),
        ),
      );
      const pack = await generateExecutivePack(
        {
          workspaceId: portfolioStory?.workspace.id || undefined,
          reportingPeriod:
            portfolioStory?.scope.reportingPeriod || data.metadata.asOf,
          comparisonPeriod:
            portfolioStory?.scope.comparisonPeriod || data.metadata.comparisonPeriod,
          filterScope: portfolioStory?.scope.filters ?? filterScope,
        },
        data.metadata.dataMode,
      );
      setAttempt({ phase: "ready", pack });
    } catch (error) {
      setAttempt({
        phase: "error",
        stage:
          error instanceof GovernedWorkflowError
            ? error.stage
            : "requesting_executive_pack",
        message:
          error instanceof Error
            ? error.message
            : "The governed export workflow returned an unknown error.",
      });
    }
  };
  return (
    <div className="executive-pack-action">
      <button
        type="button"
        className="secondary-button"
        onClick={() => void request()}
        disabled={unavailable || attempt.phase === "working"}
      >
        <span aria-hidden="true">{attempt.phase === "working" ? "…" : "↓"}</span>
        {attempt.phase === "working" ? "Generating Executive Pack" : "Export Executive Pack"}
      </button>
      {attempt.phase === "working" ? (
        <div className="pack-status tone-watch" role="status">
          <strong>{stageLabel(attempt.stage)}</strong>
          <small>Creating and validating the governed PowerPoint job…</small>
        </div>
      ) : null}
      {attempt.phase === "error" ? (
        <div className="pack-status tone-critical" role="alert">
          <strong>Failed at {stageLabel(attempt.stage)}</strong>
          <small>{attempt.message}</small>
        </div>
      ) : null}
      {attempt.phase === "ready" ? (
        <div className="pack-status tone-favourable" role="status">
          <strong>{stageLabel(attempt.pack.stage)} · {attempt.pack.filename}</strong>
          <small>
            {attempt.pack.slideCount} slides · editable PowerPoint · {attempt.pack.lastCompletedStage ? `last completed: ${stageLabel(attempt.pack.lastCompletedStage)} · ` : ""}{attempt.pack.reused ? "existing governed job reused" : "new governed job"}
          </small>
          <span>
            {attempt.pack.downloadUrl ? (
              <a href={attempt.pack.downloadUrl}>Download PowerPoint</a>
            ) : <em>Download URL unavailable</em>}
            {attempt.pack.manifestUrl ? (
              <a href={attempt.pack.manifestUrl}>Open manifest</a>
            ) : null}
          </span>
        </div>
      ) : null}
    </div>
  );
}

function alertEvidence(alert: AlertRecord): EvidenceItem {
  const lifecycle = alert.lifecycle;
  return {
    eyebrow: `Alert evidence · ${alert.id}`,
    title: alert.title,
    summary: `${alert.metric} triggered a ${alert.severity.toLowerCase()} evidence rule for ${alert.segment}.`,
    facts: [
      { label: "Current", value: alert.current },
      { label: "Baseline", value: alert.baseline },
      { label: "Rule", value: alert.threshold },
      { label: "Owner", value: alert.owner },
      { label: "Workflow state", value: alert.state },
      ...(lifecycle
        ? [
            { label: "Rule version", value: lifecycle.ruleVersion },
            {
              label: "Observation period",
              value: lifecycle.latestEvidence.period,
            },
            {
              label: "Data-quality status",
              value: lifecycle.latestEvidence.dataQualityStatus,
            },
            {
              label: "Evidence run",
              value: lifecycle.latestEvidence.runId,
            },
            {
              label: "Dataset hash",
              value: lifecycle.latestEvidence.datasetHash ?? "Not supplied by source",
            },
            {
              label: "Configuration hash",
              value: lifecycle.latestEvidence.configurationHash,
            },
            {
              label: "Audit integrity",
              value: `${lifecycle.auditIntegrity.status} · ${lifecycle.auditIntegrity.eventCount} events`,
            },
          ]
        : []),
      ...alert.evidence.map((item, index) => ({
        label: `Evidence ${index + 1}`,
        value: item,
      })),
    ],
    caveat:
      "Alert rules identify evidence that merits review. They do not make final policy or customer-level decisions.",
    action: "Confirm ownership, review the evidence pack and record the outcome.",
  };
}

export function ExecutivePage(props: PageProps) {
  const { data, mode, onOpenEvidence, onNavigate } = props;
  const loss = metric(data, "ANNUALISED_LOSS_RATE");
  const finding = data.rootCause.finding;
  const adverseMovement = finding.observedChangeBps > 0;
  const signedBps = (value: number) =>
    `${value > 0 ? "+" : ""}${value.toFixed(1)} bps`;
  const principalTrend =
    data.trends.find((series) => series.id === "ANNUALISED_LOSS_RATE") ??
    data.trends[0];
  const visibleAlerts = data.alerts.slice(0, mode === "executive" ? 3 : 4);
  const contributionLens = resolveContributionLens(
    data.rootCause.lenses,
    data.contributors,
    data.rootCause.finding.primaryDimension,
  );
  return (
    <>
      <PageHeader
        eyebrow="Portfolio command centre"
        title="Portfolio risk, explained—not merely reported."
        summary="A governed view of growth, loss, fraud, friction and expected profitability across the synthetic card portfolio."
        facts={[
          {
            label: "Portfolio status",
            value: adverseMovement ? "Targeted review" : "Continue monitoring",
            status: adverseMovement ? "Adverse" : "Favourable",
          },
          { label: "Reporting month", value: data.metadata.asOf },
          { label: "Population", value: `${data.metadata.rowCount.toLocaleString()} account-months` },
        ]}
        actions={<ExecutivePackAction props={props} />}
      />
      <ModeNote mode={mode} />

      <section className="signal-brief" aria-label="Primary portfolio signal">
        <div
          className={`signal-mark ${adverseMovement ? "tone-adverse" : "tone-favourable"}`}
        >
          <span>{adverseMovement ? "↑" : "↓"}</span>
        </div>
        <div className="signal-copy">
          <div className="eyebrow">Validated movement · {data.rootCause.finding.comparisonPeriod}</div>
          <h2>
            Loss rate {adverseMovement ? "rose" : "fell"}{" "}
            {Math.abs(finding.observedChangeBps).toFixed(1)} bps;{" "}
            {finding.primaryDriver} explains{" "}
            {Math.round(finding.contributionShare * 100)}%.
          </h2>
          <p>
            Mix and within-segment performance reconcile the movement.{" "}
            {adverseMovement
              ? "The evidence supports a targeted investigation, not a portfolio-wide tightening."
              : "The favourable movement should be monitored before drawing a durable conclusion."}
          </p>
        </div>
        <div className="signal-bridge">
          <span>
            <small>Mix</small>
            <strong>{signedBps(finding.mixContributionBps)}</strong>
          </span>
          <i aria-hidden="true">+</i>
          <span>
            <small>Performance</small>
            <strong>{signedBps(finding.withinSegmentContributionBps)}</strong>
          </span>
          <button
            type="button"
            className="text-button"
            onClick={() => onNavigate("root-cause")}
          >
            Explain movement <span aria-hidden="true">→</span>
          </button>
        </div>
      </section>

      <section className={`metric-grid ${mode === "executive" ? "executive-density" : ""}`}>
        {data.kpis.map((item) => (
          <MetricCard
            key={item.id}
            metric={item}
            trend={trendValues(data, item.id)}
            onInspect={onOpenEvidence.bind(null, buildMetricEvidence(item))}
            compact={mode === "executive"}
          />
        ))}
      </section>

      <div className="content-grid cols-8-4">
        <Panel
          eyebrow="24-month movement"
          title={principalTrend.label}
          subtitle="Portfolio scope · annualised · trailing 24 reporting months"
          action={
            <MethodologyPopover title="Annualised loss rate">
              Monthly net credit loss divided by average receivables, multiplied
              by 12. The ratio uses portfolio sums and excludes quarantined rows.
            </MethodologyPopover>
          }
        >
          <ChartInteractionFrame
            label={principalTrend.label}
            filename="naim-command-centre-loss-trend.csv"
            rows={({ range }) =>
              principalTrend.points
                .slice(-Number(range))
                .map((point) => ({
                  reporting_period: point.month,
                  value: point.value,
                  lower: point.lower,
                  upper: point.upper,
                  unit: "%",
                  metric_id: principalTrend.id,
                }))
            }
            rangeOptions={[
              { value: "6", label: "6M" },
              { value: "12", label: "12M" },
              { value: "24", label: "24M" },
            ]}
            defaultRange="24"
            onOpenEvidence={() => onOpenEvidence(buildMetricEvidence(loss))}
            onDrillThrough={() => onNavigate("trends")}
          >
            {({ range }) => (
              <TrendBars
                points={principalTrend.points.slice(-Number(range))}
                unit="%"
                label={principalTrend.label}
              />
            )}
          </ChartInteractionFrame>
        </Panel>
        <Panel
          eyebrow="Structured interpretation"
          title="What management should know"
          subtitle="Generated from validated findings"
          className="interpretation-panel"
        >
          <ol className="finding-list">
            {data.interpretation.adverse.map((finding, index) => (
              <li key={finding}>
                <span>{index + 1}</span>
                <p>{finding}</p>
              </li>
            ))}
          </ol>
          <div className="favourable-note">
            <span aria-hidden="true">↓</span>
            <p>
              <strong>Largest favourable movement</strong>
              {data.interpretation.favourable}
            </p>
          </div>
          <button
            type="button"
            className="primary-button is-wide"
            onClick={() => onNavigate("investigations")}
          >
            Open priority investigation
          </button>
        </Panel>
      </div>

      <div className="content-grid cols-7-5">
        <Panel
          eyebrow="Contribution lens"
          title="Where the deterioration sits"
          subtitle={`${contributionLens.subtitle} · dimensions are not additive`}
          action={
            <button className="text-button" type="button" onClick={() => onNavigate("root-cause")}>
              Full decomposition →
            </button>
          }
        >
          <ContributionBars
            data={data.contributors}
            onSelect={(item) =>
              onOpenEvidence({
                eyebrow: "Contribution evidence",
                title: item.label,
                summary: `${item.label} contributes ${item.contribution.toFixed(1)} basis points to the observed portfolio movement.`,
                facts: [
                  { label: "Mix contribution", value: `${item.mix.toFixed(1)} bps` },
                  { label: "Within-segment", value: `${item.performance.toFixed(1)} bps` },
                  { label: "Population", value: item.population.toLocaleString() },
                  ...(item.persistence > 0
                    ? [
                        {
                          label: "Persistence",
                          value: `${item.persistence} reporting periods`,
                        },
                      ]
                    : []),
                ],
                caveat:
                  "This is one explanatory dimension. Contributions across overlapping dimensions must not be added.",
                action: "Review the hierarchical drill path and aligned vintages.",
              })
            }
          />
        </Panel>
        <Panel
          eyebrow="Early warning"
          title={earlyWarningHeadline(visibleAlerts)}
          subtitle="Governed rule evidence with durable lifecycle, recurrence and suppression state"
          action={
            <button className="text-button" type="button" onClick={() => onNavigate("investigations")}>
              View queue →
            </button>
          }
        >
          <div className="alert-list">
            {visibleAlerts.map((alert) => (
              <button
                type="button"
                className="alert-list-item"
                key={alert.id}
                onClick={() => onOpenEvidence(alertEvidence(alert))}
              >
                <StatusChip status={alert.severity} compact />
                <span>
                  <strong>{alert.title}</strong>
                  <small>{alert.segment}</small>
                </span>
                <span className="alert-age">{alert.age}</span>
              </button>
            ))}
          </div>
          <div className="caveat-note">
            <span aria-hidden="true">i</span>
            <p>
              <strong>Data-quality caveat</strong>
              {data.interpretation.caveat}
            </p>
          </div>
        </Panel>
      </div>

      <AnalystOnly mode={mode}>
        <div className="content-grid cols-6-6">
          <Panel
            eyebrow="Delinquency migration"
            title="Adjacent-period roll rates"
            subtitle="Matched account population · prior state to current state"
          >
            <RollRateMatrix
              labels={data.rollRates.labels}
              values={data.rollRates.values}
            />
          </Panel>
          <Panel
            eyebrow="Portfolio composition"
            title="Risk-band distribution"
            subtitle="Share of active accounts · ending balance available in evidence"
          >
            <HorizontalBars
              data={data.riskDistribution}
              onSelect={(item) =>
                onOpenEvidence({
                  eyebrow: "Distribution evidence",
                  title: item.label,
                  summary: `${item.value.toFixed(1)}% of active accounts are in this synthetic risk band.`,
                  facts: [
                    { label: "Account share", value: `${item.value.toFixed(1)}%` },
                    { label: "Accounts", value: item.secondary?.toLocaleString() ?? "N/A" },
                    { label: "Status", value: item.status ?? "Stable" },
                  ],
                  caveat:
                    "Synthetic risk bands are analytical groupings and not customer-level adverse-action decisions.",
                })
              }
            />
          </Panel>
        </div>
      </AnalystOnly>

      <SourceFooter
        source="validated synthetic metric marts"
        denominator={loss.denominator}
        period={`${data.metadata.asOf} versus ${data.metadata.comparisonPeriod}`}
      />
    </>
  );
}

export function TrendsPage(props: PageProps) {
  const { data, mode, onOpenEvidence } = props;
  const [selectedMetric, setSelectedMetric] = useState(
    "ANNUALISED_LOSS_RATE",
  );
  const series =
    data.trends.find((item) => item.id === selectedMetric) ?? data.trends[0];
  const selectedKpi = metric(data, selectedMetric);
  return (
    <>
      <PageHeader
        eyebrow="Portfolio trends"
        title="Separate signal from ordinary movement."
        summary="Explore governed monthly trends with consistent period, population and denominator treatment."
        facts={[
          { label: "Observation window", value: "24 monthly periods" },
          { label: "Analytical grain", value: "Account-month" },
          { label: "Publication gate", value: data.metadata.qualityStatus, status: "Watch" },
        ]}
      />
      <ModeNote mode={mode} />
      <Panel
        eyebrow="Trend explorer"
        title={series.label}
        subtitle={`Monthly observations · unit ${series.unit} · ${data.metadata.asOf}`}
        action={
          <select
            className="compact-select"
            value={selectedMetric}
            onChange={(event) => setSelectedMetric(event.target.value)}
            aria-label="Select trend metric"
          >
            {data.trends.map((item) => (
              <option value={item.id} key={item.id}>{item.label}</option>
            ))}
          </select>
        }
      >
        <div className="trend-summary-row">
          <MetricCard
            metric={selectedKpi}
            trend={series.points.slice(-10).map((point) => point.value)}
            onInspect={() => onOpenEvidence(buildMetricEvidence(selectedKpi))}
          />
          <div className="trend-summary-copy">
            <div className="eyebrow">Signal assessment</div>
            <h3>{selectedKpi.statisticalStatus}</h3>
            <p>
              The selected movement is evaluated against materiality, persistence
              and statistical variation. A signal alone is not a causal finding.
            </p>
            <dl>
              <div>
                <dt>Current denominator</dt>
                <dd>{selectedKpi.denominator}</dd>
              </div>
              <div>
                <dt>Definition version</dt>
                <dd>{selectedKpi.definition.version}</dd>
              </div>
            </dl>
          </div>
        </div>
        <TrendBars
          points={series.points}
          unit={series.unit}
          label={series.label}
        />
      </Panel>
      <div className="content-grid cols-6-6">
        <Panel
          eyebrow="Composition"
          title="Risk-band distribution"
          subtitle="Current active account share"
        >
          <HorizontalBars data={data.riskDistribution} />
        </Panel>
        <Panel
          eyebrow="Movement reconciliation"
          title="Acquisition-channel contribution"
          subtitle="Mix plus within-segment performance"
        >
          <ContributionBars data={data.contributors} />
        </Panel>
      </div>
      <AnalystOnly mode={mode}>
        <Panel
          eyebrow="Adjacent state"
          title="Delinquency transition matrix"
          subtitle="Matched observations only; cure and roll-forward populations are aligned"
        >
          <RollRateMatrix labels={data.rollRates.labels} values={data.rollRates.values} />
        </Panel>
      </AnalystOnly>
    </>
  );
}

export function RootCausePage(props: PageProps) {
  const { data, mode, onOpenEvidence, onNavigate } = props;
  const [lens, setLens] = useState(
    data.rootCause.lenses.some(
      (item) => item.dimension === data.rootCause.finding.primaryDimension,
    )
      ? data.rootCause.finding.primaryDimension
      : data.rootCause.lenses[0]?.dimension ?? "",
  );
  const currentLens =
    data.rootCause.lenses.find((item) => item.dimension === lens) ??
    data.rootCause.lenses[0];
  const finding = data.rootCause.finding;
  const residual =
    finding.observedChangeBps -
    finding.mixContributionBps -
    finding.withinSegmentContributionBps;
  const signedBps = (value: number) =>
    `${value > 0 ? "+" : ""}${value.toFixed(1)} bps`;
  const adverse = finding.observedChangeBps > 0;
  const qualityPass =
    data.dataQuality.status.toLowerCase().includes("pass") &&
    !data.dataQuality.checks.some((check) => check.status === "Fail");
  return (
    <>
      <PageHeader
        eyebrow="Root-cause explorer"
        title={`${signedBps(finding.observedChangeBps)}, fully reconciled.`}
        summary="Data quality first, then exact mix/performance decomposition and a ranked, non-causal driver lens."
        facts={[
          {
            label: "Primary driver",
            value: finding.primaryDriver,
            status: adverse ? "Adverse" : "Favourable",
          },
          { label: "Contribution share", value: `${Math.round(finding.contributionShare * 100)}%` },
          { label: "Causal status", value: finding.causalStatus },
        ]}
      />
      <ModeNote mode={mode} />
      <section className="decomposition-equation" aria-label="Decomposition reconciliation">
        <div>
          <span>Observed change</span>
          <strong>{signedBps(finding.observedChangeBps)}</strong>
        </div>
        <i>=</i>
        <div>
          <span>Mix contribution</span>
          <strong>{signedBps(finding.mixContributionBps)}</strong>
        </div>
        <i>+</i>
        <div>
          <span>Within-segment performance</span>
          <strong>{signedBps(finding.withinSegmentContributionBps)}</strong>
        </div>
        <span className="reconcile-mark">
          ✓ Residual {residual.toFixed(3)} bps
        </span>
      </section>
      <div className="content-grid cols-8-4">
        <Panel
          eyebrow="Exact rate decomposition"
          title="Mix versus performance"
          subtitle="Choose one explanatory lens; overlapping dimensions are not added"
          action={
            <select
              className="compact-select"
              value={lens}
              onChange={(event) => setLens(event.target.value)}
              aria-label="Select decomposition dimension"
            >
              {data.rootCause.lenses.map((item) => (
                <option key={item.dimension}>{item.dimension}</option>
              ))}
            </select>
          }
        >
          <ChartInteractionFrame
            label={`${currentLens?.dimension ?? "Returned"} root-cause decomposition`}
            filename="naim-root-cause-decomposition.csv"
            rows={(currentLens?.items ?? []).map((item) => ({
              dimension: currentLens?.dimension ?? "Not returned",
              member: item.label,
              mix_contribution_bps: item.mix,
              within_segment_contribution_bps: item.performance,
              total_contribution_bps: item.contribution,
              population: item.population,
              persistence_periods: item.persistence,
            }))}
            series={[
              { id: "mix", label: "Mix" },
              { id: "performance", label: "Within-segment" },
            ]}
            onOpenEvidence={() =>
              onOpenEvidence({
                eyebrow: "Root-cause reconciliation evidence",
                title: `${currentLens?.dimension ?? "Returned dimension"} decomposition`,
                summary: `Observed movement ${signedBps(finding.observedChangeBps)} reconciles to mix and within-segment performance with ${residual.toFixed(3)} bps residual.`,
                facts: [
                  { label: "Dimension", value: currentLens?.dimension ?? "Not returned" },
                  { label: "Observed movement", value: signedBps(finding.observedChangeBps) },
                  { label: "Mix", value: signedBps(finding.mixContributionBps) },
                  { label: "Within-segment", value: signedBps(finding.withinSegmentContributionBps) },
                  { label: "Reconciliation residual", value: `${residual.toFixed(3)} bps` },
                ],
                caveat: "A reconciled contribution is an observed decomposition, not causal proof.",
              })
            }
            onDrillThrough={() => onNavigate("vintage")}
          >
            {({ activeSeries }) => (
              <ContributionBars
                data={currentLens?.items ?? []}
                showMix={activeSeries.has("mix")}
                showPerformance={activeSeries.has("performance")}
                onSelect={(item) =>
                  onOpenEvidence({
                    eyebrow: `${currentLens?.dimension ?? "Returned"} lens`,
                    title: item.label,
                    summary: `${item.label} explains ${item.contribution.toFixed(1)} bps in this separately reconciled dimension.`,
                    facts: [
                      { label: "Mix", value: `${item.mix.toFixed(1)} bps` },
                      { label: "Performance", value: `${item.performance.toFixed(1)} bps` },
                      { label: "Total", value: `${item.contribution.toFixed(1)} bps` },
                      { label: "Population", value: item.population.toLocaleString() },
                      ...(item.persistence > 0
                        ? [{ label: "Persistence", value: `${item.persistence} periods` }]
                        : []),
                    ],
                    caveat:
                      "The decomposition is exact for this dimension. It does not prove why account-level behaviour changed.",
                    action: "Inspect the hierarchical path and maturity-aligned vintages.",
                  })
                }
              />
            )}
          </ChartInteractionFrame>
          <div className="reconciliation-foot">
            <span>Dimension total</span>
            <strong>{currentLens?.total.toFixed(1)} bps</strong>
            <span>Residual</span>
            <strong>{residual.toFixed(3)} bps</strong>
          </div>
        </Panel>
        <Panel
          eyebrow="Quality gate"
          title={
            qualityPass
              ? "Business diagnosis passed the publication gate"
              : "Publication gate requires attention"
          }
          subtitle="Current run quality status; warnings and failures remain visible"
          className="quality-gate-panel"
        >
          <div className="quality-score-mini">
            <span>{data.dataQuality.score.toFixed(1)}</span>
            <small>/ 100</small>
          </div>
          <StatusChip status={qualityPass ? "Favourable" : "Critical"} />
          <p>{data.interpretation.caveat}</p>
          <button
            type="button"
            className="secondary-button is-wide"
            onClick={() => onNavigate("data-quality")}
          >
            Inspect publication gate
          </button>
        </Panel>
      </div>
      <Panel
        eyebrow="Ranked driver lens"
        title={`Largest contributions within ${finding.primaryDimension.replaceAll("_", " ")}`}
        subtitle="One separately reconciled dimension; this is not a nested causal path"
      >
        <div className="drill-path">
          {data.rootCause.hierarchy.map((node, index) => (
            <button
              type="button"
              className="drill-node"
              key={node.level}
              onClick={() =>
                onOpenEvidence({
                  eyebrow: `Drill level · ${node.level}`,
                  title: node.value,
                  summary: `${node.value} contributes ${node.contribution.toFixed(1)} bps at this point in the concentrated path.`,
                  facts: [
                    { label: "Contribution", value: `${node.contribution.toFixed(1)} bps` },
                    { label: "Portfolio share", value: `${(node.share * 100).toFixed(0)}%` },
                    { label: "Population", value: node.population.toLocaleString() },
                  ],
                  caveat:
                    "Each child is selected within its parent population; percentages are not independent portfolio partitions.",
                })
              }
            >
              <span>{node.level}</span>
              <strong>{node.value}</strong>
              <small>
                {node.contribution.toFixed(1)} bps · {(node.share * 100).toFixed(0)}%
              </small>
              {index < data.rootCause.hierarchy.length - 1 ? (
                <i aria-hidden="true">→</i>
              ) : null}
            </button>
          ))}
        </div>
      </Panel>
      <div className="content-grid cols-6-6">
        <Panel
          eyebrow="Behavioural extension"
          title="Model-based driver attribution"
          subtitle="Not returned by the governed live endpoint"
        >
          {data.rootCause.behaviouralDrivers.length > 0 ? (
            <HorizontalBars data={data.rootCause.behaviouralDrivers} unit="%" />
          ) : (
            <DataState
              type="empty"
              title="No live SHAP evidence"
              detail="The API returns exact aggregate decomposition only. Model-based attribution remains a documented extension."
            />
          )}
        </Panel>
        <Panel
          eyebrow="Controlled response"
          title="Recommended investigation sequence"
          subtitle="Analytical response, not final credit policy"
        >
          <ol className="investigation-steps">
            {finding.recommendedInvestigation.map((step, index) => (
              <li key={step}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <p>{step}</p>
              </li>
            ))}
          </ol>
          <button
            type="button"
            className="primary-button is-wide"
            onClick={() => onNavigate("investigations")}
          >
            Open investigation workflow
          </button>
        </Panel>
      </div>
    </>
  );
}

export function VintagePage(props: PageProps) {
  const { data, mode, onOpenEvidence } = props;
  const [view, setView] = useState<"heatmap" | "curves">("heatmap");
  const [metricName, setMetricName] = useState<
    "delinquency30" | "cumulativeLoss"
  >("delinquency30");
  const cells = data.vintages;
  const weak = cells
    .filter(
      (cell) =>
        cell.mob >= 4 && cell.mob <= 8 && !cell.maturityWarning,
    )
    .sort((a, b) => b.delinquency30 - a.delinquency30)[0];
  return (
    <>
      <PageHeader
        eyebrow="Vintage explorer"
        title="Maturity aligned. Cohort sized. Confidence shown."
        summary="Compare origination cohorts at the same months-on-book without overstating incomplete young vintages."
        facts={[
          { label: "Weakest aligned cohort", value: weak?.vintage ?? "N/A", status: "Adverse" },
          { label: "Scope", value: weak?.channel ?? "N/A" },
          { label: "Cohorts in scope", value: new Set(cells.map((cell) => cell.vintage)).size.toString() },
        ]}
      />
      <ModeNote mode={mode} />
      <Panel
        eyebrow="Cohort performance"
        title={metricName === "delinquency30" ? "30+ delinquency by months on book" : "Cumulative net loss by months on book"}
        subtitle="Original booked cohort denominator · 95% Wilson interval in evidence"
        action={
          <div className="panel-control-row">
            <SegmentedControl
              label="Vintage metric"
              value={metricName}
              options={[
                { value: "delinquency30", label: "30+ delinquency" },
                { value: "cumulativeLoss", label: "Cumulative loss" },
              ]}
              onChange={setMetricName}
            />
            <SegmentedControl
              label="Vintage view"
              value={view}
              options={[
                { value: "heatmap", label: "Heatmap" },
                { value: "curves", label: "Curves" },
              ]}
              onChange={setView}
            />
          </div>
        }
      >
        <ChartInteractionFrame
          label="Maturity-aligned vintage analysis"
          filename="naim-vintage-analysis.csv"
          rows={cells.map((cell) => ({
            vintage: cell.vintage,
            months_on_book: cell.mob,
            channel: cell.channel,
            cohort_size: cell.cohortSize,
            delinquency_30_percent: cell.delinquency30,
            cumulative_loss_percent: cell.cumulativeLoss,
            confidence_low: cell.confidenceLow,
            confidence_high: cell.confidenceHigh,
            maturity_warning: cell.maturityWarning,
          }))}
          onOpenEvidence={() => {
            if (!weak) return;
            onOpenEvidence({
              eyebrow: "Maturity-aligned cohort evidence",
              title: `${weak.vintage} · month ${weak.mob}`,
              summary: `${weak.channel} is the calculated concentration at the selected common-maturity point.`,
              facts: [
                { label: "Population", value: weak.cohortSize.toLocaleString() },
                { label: "30+ delinquency", value: `${weak.delinquency30.toFixed(2)}%` },
                { label: "Cumulative net loss", value: `${weak.cumulativeLoss.toFixed(2)}%` },
                { label: "95% interval", value: `${weak.confidenceLow.toFixed(2)}%–${weak.confidenceHigh.toFixed(2)}%` },
                { label: "Maturity warning", value: weak.maturityWarning ? "Incomplete" : "None" },
              ],
              caveat: "Young cohorts are compared only at common maturity.",
            });
          }}
        >
          {() => view === "heatmap" ? (
            <VintageHeatmap
              cells={cells}
              metric={metricName}
              onSelect={(cell) =>
                onOpenEvidence({
                  eyebrow: "Maturity-aligned cohort evidence",
                  title: `${cell.vintage} · month ${cell.mob}`,
                  summary: `${cell.channel} performance at the selected maturity point.`,
                  facts: [
                    { label: "30+ delinquency", value: `${cell.delinquency30.toFixed(2)}%` },
                    { label: "Cumulative net loss", value: `${cell.cumulativeLoss.toFixed(2)}%` },
                    { label: "95% interval", value: `${cell.confidenceLow.toFixed(2)}%–${cell.confidenceHigh.toFixed(2)}%` },
                    { label: "Original cohort", value: cell.cohortSize.toLocaleString() },
                    { label: "Maturity status", value: cell.maturityWarning ? "Incomplete" : "Mature to comparison horizon" },
                  ],
                  caveat:
                    "Young cohorts are compared only at common maturity. Cumulative outcomes may continue to develop.",
                  action: "Review acquisition quality and strategy exposure for the aligned cohort.",
                })
              }
            />
          ) : (
            <CohortCurves cells={cells} metric={metricName} />
          )}
        </ChartInteractionFrame>
      </Panel>
      <div className="content-grid cols-8-4">
        <Panel
          eyebrow="Aligned cohort diagnostics"
          title={
            weak
              ? `Why ${weak.vintage} is the weakest aligned cohort`
              : "Maturity-aligned cohort diagnostics"
          }
          subtitle="MOB 4–8 comparison"
        >
          <TableShell label="Vintage diagnostic table">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Vintage</th>
                  <th>Scope</th>
                  <th>Cohort</th>
                  <th>MOB 4</th>
                  <th>MOB 6</th>
                  <th>MOB 8</th>
                  <th>Maturity</th>
                </tr>
              </thead>
              <tbody>
                {[...new Set(cells.map((cell) => cell.vintage))].map((vintage) => {
                  const rows = cells.filter((cell) => cell.vintage === vintage);
                  return (
                    <tr key={vintage}>
                      <th scope="row">{vintage}</th>
                      <td>{rows[0]?.channel}</td>
                      <td>{rows[0]?.cohortSize.toLocaleString()}</td>
                      {[4, 6, 8].map((mob) => (
                        <td key={mob}>
                          {rows.find((row) => row.mob === mob)
                            ? `${rows.find((row) => row.mob === mob)?.[metricName].toFixed(2)}%`
                            : "—"}
                        </td>
                      ))}
                      <td>
                        <StatusChip
                          status={rows.length >= 8 ? "Stable" : "Watch"}
                          compact
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </TableShell>
        </Panel>
        <Panel
          eyebrow="Maturity guardrail"
          title="Young cohorts are not ranked as mature"
          subtitle="Configured comparison rule"
          className="rule-panel"
        >
          <div className="rule-illustration">
            <span>MOB 1</span><i />
            <span>MOB 4</span><i />
            <span>MOB 8</span>
          </div>
          <p>
            Comparisons stop at the youngest cohort’s latest observed month.
            Cohort size and uncertainty travel with every value.
          </p>
          <dl>
            <div><dt>Minimum cohort</dt><dd>30</dd></div>
            <div><dt>Interval</dt><dd>95% Wilson</dd></div>
            <div><dt>Normalisation</dt><dd>Booked accounts</dd></div>
          </dl>
        </Panel>
      </div>
    </>
  );
}

export function StrategyPage(props: PageProps) {
  const { data, mode, onOpenEvidence } = props;
  const [selectedMetric, setSelectedMetric] = useState<
    "expectedProfit" | "fraudBps" | "reviewRate" | "frictionRate" | "lossRate"
  >("expectedProfit");
  const challenger = data.strategies.find((row) => row.strategy === "Challenger B");
  const champion = data.strategies.find((row) => row.strategy === "Champion A");
  const recommendation = data.strategyRecommendation;
  const decision = recommendation?.decision ?? "Review";
  const principalAccounts =
    (challenger?.eligibleAccounts ?? 0) + (champion?.eligibleAccounts ?? 0);
  const validityConcern = data.strategyValidity.some(
    (item) => item.status === "Critical" || item.status === "Adverse",
  );
  return (
    <>
      <PageHeader
        eyebrow="Strategy impact lab"
        title="Compare fraud, credit, friction and profit together."
        summary="Champion–challenger evidence combines statistical validity, practical significance and explicit loss, friction and operations guardrails."
        facts={[
          {
            label: "Deterministic outcome",
            value: decision,
            status: validityConcern ? "Adverse" : "Stable",
          },
          {
            label: "Validity state",
            value: validityConcern ? "Review required" : "Checks passed",
          },
          {
            label: "Principal arms",
            value: `${principalAccounts.toLocaleString()} accounts`,
          },
        ]}
      />
      <ModeNote mode={mode} />
      <section className="recommendation-banner">
        <div className="recommendation-grade">{decision.toUpperCase()}</div>
        <div>
          <div className="eyebrow">Configured recommendation framework</div>
          <h2>
            {recommendation?.rulePath[0] ??
              "Review the governed comparison evidence before changing strategy."}
          </h2>
          <p>{recommendation?.notice ?? "Human review and approval required."}</p>
        </div>
        <div className="recommendation-metrics">
          <span>
            <small>Fraud difference</small>
            <strong>
              {challenger && champion
                ? `${(challenger.fraudBps - champion.fraudBps).toFixed(1)} bps`
                : "N/A"}
            </strong>
          </span>
          <span>
            <small>Review difference</small>
            <strong>
              {challenger && champion
                ? `${challenger.reviewRate - champion.reviewRate > 0 ? "+" : ""}${(challenger.reviewRate - champion.reviewRate).toFixed(1)} pp`
                : "N/A"}
            </strong>
          </span>
          <span>
            <small>Profit difference</small>
            <strong>
              {challenger && champion
                ? formatCompact(challenger.expectedProfit - champion.expectedProfit, "$m")
                : "N/A"}
            </strong>
          </span>
        </div>
      </section>
      <div className="content-grid cols-7-5">
        <Panel
          eyebrow="Outcome comparison"
          title="Champion A versus challengers"
          subtitle="User-selected eligible population · observed test period"
          action={
            <select
              className="compact-select"
              value={selectedMetric}
              onChange={(event) =>
                setSelectedMetric(
                  event.target.value as typeof selectedMetric,
                )
              }
              aria-label="Select strategy metric"
            >
              <option value="expectedProfit">Expected profit</option>
              <option value="fraudBps">Fraud bps</option>
              <option value="reviewRate">Manual review</option>
              <option value="frictionRate">Customer friction</option>
              <option value="lossRate">Loss rate</option>
            </select>
          }
        >
          <ChartInteractionFrame
            label="Strategy outcome comparison"
            filename="naim-strategy-comparison.csv"
            rows={({ activeSeries }) =>
              data.strategies
                .filter((row) => activeSeries.has(row.strategy))
                .map((row) => ({
                  strategy: row.strategy,
                  eligible_accounts: row.eligibleAccounts,
                  assignment_share_percent: row.assignmentShare,
                  loss_rate_percent: row.lossRate,
                  fraud_bps: row.fraudBps,
                  review_rate_percent: row.reviewRate,
                  false_positive_rate_percent: row.falsePositiveRate,
                  friction_rate_percent: row.frictionRate,
                  complaints_per_thousand: row.complaintsPerThousand,
                  expected_profit_usd_m: row.expectedProfit,
                  validity_status: row.status,
                }))
            }
            series={data.strategies.map((row) => ({ id: row.strategy, label: row.strategy }))}
            onOpenEvidence={() =>
              onOpenEvidence({
                eyebrow: "Strategy comparison evidence",
                title: "Champion A versus Challenger B",
                summary: recommendation?.rulePath[0] ?? "The configured strategy rule returned a review outcome.",
                facts: [
                  { label: "Decision", value: decision },
                  { label: "Validity", value: validityConcern ? "Review required" : "Checks passed" },
                  { label: "Eligible accounts", value: principalAccounts.toLocaleString() },
                  { label: "Evidence status", value: "Associational comparison; approval required" },
                ],
                caveat: "Observed test differences do not authorise automatic customer-level strategy changes.",
              })
            }
          >
            {({ activeSeries }) => (
              <StrategyComparison
                rows={data.strategies}
                selectedMetric={selectedMetric}
                visibleStrategies={activeSeries}
              />
            )}
          </ChartInteractionFrame>
          <div className="strategy-legend-note">
            <span>Assignment share sums to {data.strategies.reduce((sum, row) => sum + row.assignmentShare, 0).toFixed(1)}%</span>
            <span>Unrounded values retained internally</span>
          </div>
        </Panel>
        <Panel
          eyebrow="Test validity"
          title={
            validityConcern
              ? "Validity checks require review"
              : "Evidence can support comparison"
          }
          subtitle="Validity and guardrails are assessed separately"
        >
          <div className="validity-list">
            {data.strategyValidity.map((test) => (
              <button
                type="button"
                key={test.test}
                onClick={() =>
                  onOpenEvidence({
                    eyebrow: "Strategy validity evidence",
                    title: test.test,
                    summary: test.detail,
                    facts: [
                      { label: "Result", value: test.result },
                      { label: "Status", value: test.status },
                    ],
                    caveat:
                      "Statistical validity does not automatically imply commercial or operational acceptability.",
                  })
                }
              >
                <span>
                  <strong>{test.test}</strong>
                  <small>{test.detail}</small>
                </span>
                <span>
                  <StatusChip status={test.status} compact />
                  <b>{test.result}</b>
                </span>
              </button>
            ))}
          </div>
        </Panel>
      </div>
      <Panel
        eyebrow="Comparison table"
        title="Cross-domain strategy outcomes"
        subtitle="All metrics use eligible, resolved populations and explicit denominators"
      >
        <TableShell label="Strategy comparison results">
          <table className="data-table strategy-table">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Eligible</th>
                <th>Share</th>
                <th>Loss rate</th>
                <th>Fraud</th>
                <th>Review</th>
                <th>False positive</th>
                <th>Friction</th>
                <th>Complaints / 1k</th>
                <th>Expected profit</th>
              </tr>
            </thead>
            <tbody>
              {data.strategies.map((row) => (
                <tr key={row.strategy}>
                  <th scope="row">
                    {row.strategy}
                    <small>{row.status}</small>
                  </th>
                  <td>{row.eligibleAccounts.toLocaleString()}</td>
                  <td>{row.assignmentShare.toFixed(1)}%</td>
                  <td>{row.lossRate.toFixed(2)}%</td>
                  <td>{row.fraudBps.toFixed(1)} bps</td>
                  <td>{row.reviewRate.toFixed(1)}%</td>
                  <td>{row.falsePositiveRate.toFixed(1)}%</td>
                  <td>{row.frictionRate.toFixed(1)}%</td>
                  <td>{row.complaintsPerThousand.toFixed(1)}</td>
                  <td>{formatCompact(row.expectedProfit, "$m")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableShell>
      </Panel>
      <AnalystOnly mode={mode}>
        <Panel
          eyebrow="Exact rule path"
          title={`Why the framework returned “${decision}”`}
          subtitle="The governed rule engine determines the result; commentary does not"
        >
          <div className="rule-path">
            {[
              ...(recommendation?.rulePath ?? []).map((detail) => [
                "Governed rule",
                "Review",
                detail,
              ]),
              [
                "Decision",
                decision,
                recommendation?.approvalRequired
                  ? "Human approval required"
                  : "No additional approval flag returned",
              ],
            ].map(([title, result, detail], index) => (
              <div className="rule-step" key={title}>
                <span>{index + 1}</span>
                <div>
                  <small>{title}</small>
                  <strong>{result}</strong>
                  <p>{detail}</p>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </AnalystOnly>
    </>
  );
}

function EntityControlTower({
  props,
  domain,
}: {
  props: PageProps;
  domain: "Partner" | "Vendor" | "Membership";
}) {
  const { data, mode, onOpenEvidence } = props;
  const rows =
    domain === "Partner"
      ? data.partners
      : domain === "Vendor"
        ? data.vendors
        : data.memberships;
  const [selected, setSelected] = useState(rows[0]?.id ?? "");
  const [scenario, setScenario] = useState(domain === "Vendor" ? 25 : 10);
  const active = rows.find((row) => row.id === selected) ?? rows[0];
  const averageScore =
    rows.reduce((sum, row) => sum + row.score, 0) / Math.max(rows.length, 1);
  const adverse = rows.filter(
    (row) => row.trend === "Adverse" || row.trend === "Critical",
  ).length;
  const totalScale = rows.reduce((sum, row) => sum + row.scale, 0);
  const liveSnapshot = isApiBacked(data);
  const title =
    domain === "Partner"
      ? "Partner Portfolio Control Tower"
      : domain === "Vendor"
        ? "Vendor Oversight Control Tower"
        : "Customer and Membership Value–Risk Studio";
  const summary =
    domain === "Partner"
      ? "Connect acquisition, engagement, economics, risk, service and concentration for every fictional partner."
      : domain === "Vendor"
        ? "Balance quality, capacity, cost, customer impact, concentration and exit readiness across synthetic service providers."
        : "Compare membership growth, engagement, benefit cost, loss, retention and risk-adjusted contribution.";
  return (
    <>
      <PageHeader
        eyebrow={`${domain.toLowerCase()} portfolio`}
        title={title}
        summary={summary}
        facts={[
          { label: `Active ${domain.toLowerCase()}s`, value: rows.length.toString() },
          { label: "Average score", value: `${averageScore.toFixed(0)} / 100` },
          {
            label: "Adverse / critical",
            value: adverse.toString(),
            status: adverse > 0 ? "Adverse" : "Stable",
          },
        ]}
      />
      <ModeNote mode={mode} />
      <section className="domain-kpis">
        {[
          {
            label:
              domain === "Vendor"
                ? "Process volume"
                : domain === "Membership"
                  ? "Active members"
                  : "Attributed transaction value",
            value:
              domain === "Membership"
                ? Math.round(totalScale).toLocaleString()
                : `${totalScale.toFixed(1)}${domain === "Vendor" ? "k cases" : "m"}`,
            change: liveSnapshot ? "Current API snapshot" : "+7.4% vs prior",
          },
          {
            label:
              domain === "Vendor"
                ? "Total vendor cost"
                : domain === "Membership"
                  ? "Expected contribution"
                  : "Net contribution",
            value:
              domain === "Vendor"
                ? formatCompact(
                    Math.abs(rows.reduce((sum, row) => sum + row.profit, 0)),
                    "$m",
                  )
                : formatCompact(rows.reduce((sum, row) => sum + row.profit, 0), "$m"),
            change: liveSnapshot
              ? "Current API snapshot"
              : domain === "Vendor"
                ? "+4.8%"
                : "−3.1% vs prior",
          },
          {
            label:
              domain === "Vendor"
                ? "First-time-right"
                : domain === "Membership"
                  ? "Benefit engagement"
                  : "Service-level performance",
            value: `${(rows.reduce((sum, row) => sum + row.serviceMetric, 0) / Math.max(rows.length, 1)).toFixed(1)}%`,
            ...(domain === "Partner" && liveSnapshot
              ? { value: "Not returned" }
              : {}),
            change: liveSnapshot ? "Current API snapshot" : "Stable",
          },
          {
            label: "Top concentration",
            value: `${Math.max(...rows.map((row) => row.concentration)).toFixed(1)}%`,
            change: domain === "Vendor" ? "Above watch level" : "Within range",
          },
        ].map((item) => (
          <div className="domain-kpi" key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            <small>{item.change}</small>
          </div>
        ))}
      </section>
      <div className="content-grid cols-7-5">
        <Panel
          eyebrow="Comparative rating"
          title={`${domain} scorecard`}
          subtitle="Transparent 0–100 internal analytical grade · not an agency rating"
          action={
            <select
              className="compact-select"
              value={selected}
              onChange={(event) => setSelected(event.target.value)}
              aria-label={`Select ${domain.toLowerCase()}`}
            >
              {rows.map((row) => (
                <option value={row.id} key={row.id}>{row.name}</option>
              ))}
            </select>
          }
        >
          {active ? (
            <div className="entity-scorecard">
              <div className={`entity-score tone-${active.trend.toLowerCase()}`}>
                <strong>{active.score.toFixed(1)}</strong>
                <span>/100</span>
                <small>{active.grade}</small>
              </div>
              {!liveSnapshot ? (
              <div className="score-components">
                {[
                  ["Scale / engagement", Math.min(100, active.scale * (domain === "Membership" ? 0.012 : 2.2))],
                  ...(liveSnapshot
                    ? []
                    : [
                        [
                          "Growth",
                          Math.max(0, Math.min(100, active.growth * 3 + 48)),
                        ],
                      ]),
                  ...(domain === "Partner" && liveSnapshot
                    ? []
                    : [["Service / quality", active.serviceMetric]]),
                  ["Risk control", Math.max(0, 100 - active.riskMetric * 3)],
                  ["Concentration", Math.max(0, 100 - active.concentration * 1.6)],
                ].map(([label, rawValue]) => {
                  const value = Number(rawValue);
                  return (
                    <div className="score-component" key={String(label)}>
                      <span><b>{String(label)}</b><small>{value.toFixed(0)}</small></span>
                      <i><em style={{ width: `${value}%` }} /></i>
                    </div>
                  );
                })}
              </div>
              ) : null}
              <div className="entity-detail">
                <div className="eyebrow">{active.id} · {active.category}</div>
                <h3>{active.name}</h3>
                <p>{active.status}</p>
                <dl>
                  <div><dt>Region</dt><dd>{active.region}</dd></div>
                  <div><dt>Growth</dt><dd>{liveSnapshot ? "N/A" : `${active.growth.toFixed(1)}%`}</dd></div>
                  <div><dt>{domain === "Vendor" ? "Cost" : "Expected profit"}</dt><dd>{formatCompact(active.profit, "$m")}</dd></div>
                </dl>
              </div>
            </div>
          ) : null}
        </Panel>
        <Panel
          eyebrow="Portfolio map"
          title={
            domain === "Vendor"
              ? "Quality versus process volume"
              : domain === "Membership"
                ? "Engagement versus contribution"
                : liveSnapshot
                  ? "Fraud risk versus contribution"
                  : "Growth versus contribution"
          }
          subtitle="Select a point to inspect evidence"
        >
          <QuadrantChart
            items={rows}
            xLabel={domain === "Membership" ? "Member scale" : "Scale"}
            yLabel={
              domain === "Vendor"
                ? "Service"
                : domain === "Partner" && liveSnapshot
                  ? "Fraud bps"
                : "Growth"
            }
            xValue={(item) =>
              rows.find((row) => row.id === item.id)?.scale ?? 0
            }
            yValue={(item) =>
              domain === "Vendor"
                ? rows.find((row) => row.id === item.id)?.serviceMetric ?? 0
                : domain === "Partner" && liveSnapshot
                  ? rows.find((row) => row.id === item.id)?.riskMetric ?? 0
                : rows.find((row) => row.id === item.id)?.growth ?? 0
            }
            onSelect={(item) => setSelected(item.id)}
          />
        </Panel>
      </div>
      <Panel
        eyebrow={`${domain} portfolio`}
        title="Performance, risk and economics"
        subtitle="Peer grade and current-period analytical status"
      >
        <TableShell label={`${domain} portfolio table`}>
          <table className="data-table entity-table">
            <thead>
              <tr>
                <th>{domain}</th>
                <th>Category</th>
                <th>Region</th>
                <th>Scale</th>
                <th>Growth</th>
                <th>{domain === "Vendor" ? "Cost" : "Expected profit"}</th>
                <th>Risk</th>
                <th>Service</th>
                <th>Concentration</th>
                <th>Grade</th>
                <th>Trend</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className={selected === row.id ? "is-selected" : ""}
                  onClick={() => setSelected(row.id)}
                >
                  <th scope="row">
                    {row.name}
                    <small>{row.id}</small>
                  </th>
                  <td>{row.category}</td>
                  <td>{row.region}</td>
                  <td>{row.scale.toLocaleString()}</td>
                  <td>{liveSnapshot ? "N/A" : `${row.growth.toFixed(1)}%`}</td>
                  <td>{formatCompact(row.profit, "$m")}</td>
                  <td>{row.riskMetric.toFixed(1)}</td>
                  <td>
                    {domain === "Partner" && liveSnapshot
                      ? "N/A"
                      : `${row.serviceMetric.toFixed(1)}%`}
                  </td>
                  <td>{row.concentration.toFixed(1)}%</td>
                  <td>
                    <strong>{row.score.toFixed(1)}</strong>
                    <small>{row.grade.replace(/^Grade \d+:\s*/, "")}</small>
                  </td>
                  <td><StatusChip status={row.trend} compact /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableShell>
      </Panel>
      {liveSnapshot ? (
        <Panel
          eyebrow={`${domain} scenario`}
          title="Scenario service unavailable in this view"
          subtitle="No local sensitivity values are substituted for API results"
        >
          <DataState
            type="empty"
            title="No governed scenario payload"
            detail="This endpoint supplies current entity performance only. Scenario controls remain disabled until a governed scenario endpoint returns results."
          />
        </Panel>
      ) : (
      <Panel
        eyebrow={domain === "Membership" ? "Benefit scenario" : `${domain} scenario`}
        title={
          domain === "Vendor"
            ? "Controlled volume reallocation"
            : domain === "Partner"
              ? "Partner substitution preview"
              : "Benefit-cost sensitivity"
        }
        subtitle="Scenario estimate · not a committed management decision"
        className="scenario-strip-panel"
      >
        <div className="scenario-strip">
          <div className="scenario-controls">
            <span>Change magnitude</span>
            <SegmentedControl
              label="Scenario magnitude"
              value={String(scenario)}
              options={(domain === "Vendor" ? [10, 25, 50] : [5, 10, 20]).map(
                (value) => ({ value: String(value), label: `${value}%` }),
              )}
              onChange={(value) => setScenario(Number(value))}
            />
          </div>
          {[
            ["Expected cost", `${scenario > 20 ? "+" : "−"}$${(scenario * 0.013).toFixed(2)}m`, scenario > 20 ? "Adverse" : "Stable"],
            ["Concentration", `${(Math.max(...rows.map((row) => row.concentration)) - scenario * 0.18).toFixed(1)}%`, "Favourable"],
            ["Capacity / coverage", `${Math.max(72, 100 - scenario * 0.65).toFixed(0)}%`, scenario > 25 ? "Adverse" : "Watch"],
            ["Customer impact", `${Math.round(scenario * totalScale * 4.1).toLocaleString()} units`, "Watch"],
          ].map(([label, value, itemStatus]) => (
            <div className="scenario-result" key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
              <StatusChip status={itemStatus} compact />
            </div>
          ))}
          <button
            type="button"
            className="primary-button"
            onClick={() =>
              onOpenEvidence({
                eyebrow: "Scenario evidence",
                title: `${scenario}% ${domain.toLowerCase()} scenario`,
                summary:
                  "The preview applies configured synthetic elasticities to the selected portfolio.",
                facts: [
                  { label: "Magnitude", value: `${scenario}%` },
                  { label: "Selected entity", value: active?.name ?? "N/A" },
                  {
                    label: "Method",
                    value: "Illustrative local sensitivity; not persisted",
                  },
                ],
                caveat:
                  "This local UI sensitivity uses simplified arithmetic. It is not returned by the live entity API and is not a forecast, contract decision or regulatory capital measure.",
              })
            }
          >
            Inspect assumptions
          </button>
        </div>
      </Panel>
      )}
    </>
  );
}

export function PartnersPage(props: PageProps) {
  return <EntityControlTower props={props} domain="Partner" />;
}

export function VendorsPage(props: PageProps) {
  return <EntityControlTower props={props} domain="Vendor" />;
}

export function MembershipPage(props: PageProps) {
  const [transitionMode, setTransitionMode] = useState<"count" | "rate">("rate");
  const apiBacked = isApiBacked(props.data);
  return (
    <>
      <EntityControlTower props={props} domain="Membership" />
      {apiBacked ? (
        <Panel
          eyebrow="Membership movement"
          title="Tier transition matrix unavailable"
          subtitle="No demonstration transition matrix is substituted for the API"
        >
          <DataState
            type="empty"
            title="Membership transitions were not returned"
            detail="This page will enable the matrix when a governed membership-transition payload is connected."
          />
        </Panel>
      ) : (
      <Panel
        eyebrow="Membership movement"
        title="Tier transition matrix"
        subtitle="Synthetic member transitions · current tier by prior tier"
        action={
          <SegmentedControl
            label="Transition display"
            value={transitionMode}
            options={[
              { value: "rate", label: "Rate" },
              { value: "count", label: "Count" },
            ]}
            onChange={setTransitionMode}
          />
        }
      >
        <RollRateMatrix
          labels={["Core", "Silver", "Gold", "Platinum", "Premium Business"]}
          values={
            transitionMode === "rate"
              ? [
                  [91.4, 6.8, 1.1, 0.3, 0.4],
                  [4.9, 89.2, 4.3, 1.1, 0.5],
                  [1.2, 3.1, 90.4, 4.6, 0.7],
                  [0.4, 0.8, 2.9, 94.2, 1.7],
                  [0.7, 0.5, 0.8, 1.2, 96.8],
                ]
              : [
                  [7522, 560, 91, 25, 32],
                  [314, 5718, 276, 71, 31],
                  [63, 163, 4764, 242, 38],
                  [13, 26, 95, 3080, 56],
                  [11, 8, 12, 18, 1451],
                ]
          }
        />
      </Panel>
      )}
    </>
  );
}

export function BasketsPage(props: PageProps) {
  const { data, mode, onOpenEvidence } = props;
  const liveDefinitions = isApiBacked(data);
  const [leftId, setLeftId] = useState(data.baskets[0]?.id ?? "");
  const [rightId, setRightId] = useState(data.baskets[1]?.id ?? "");
  const [operation, setOperation] = useState<"union" | "intersect" | "except">(
    "intersect",
  );
  const left = data.baskets.find((basket) => basket.id === leftId);
  const right = data.baskets.find((basket) => basket.id === rightId);
  const estimatedMembers = useMemo(() => {
    if (!left || !right) return 0;
    if (operation === "union")
      return Math.round(left.memberCount + right.memberCount * 0.72);
    if (operation === "except")
      return Math.max(0, Math.round(left.memberCount - right.memberCount * 0.18));
    return Math.round(Math.min(left.memberCount, right.memberCount) * 0.29);
  }, [left, right, operation]);
  return (
    <>
      <PageHeader
        eyebrow="Basket and workspace engine"
        title="Save the analytical question—not just the chart."
        summary="Versioned cross-domain baskets preserve population logic, grain, weighting, approval and repeatability."
        facts={[
          { label: "Saved baskets", value: data.baskets.length.toString() },
          { label: "Approved / locked", value: data.baskets.filter((basket) => basket.approved).length.toString() },
          { label: "Current grain", value: "Account-month" },
        ]}
        actions={
          <span
            className="read-only-action"
            title="Basket creation is available through the versioned API; this page is a read-only review."
          >
            Read-only definitions
          </span>
        }
      />
      <ModeNote mode={mode} />
      <section className="basket-grid">
        {data.baskets.map((basket) => (
          <button
            type="button"
            className="basket-card"
            key={basket.id}
            onClick={() =>
              onOpenEvidence({
                eyebrow: `${basket.type} basket · ${basket.id}`,
                title: basket.name,
                summary: basket.definition,
                facts: [
                  { label: "Members", value: basket.memberCount.toLocaleString() },
                  { label: "Version", value: basket.version },
                  { label: "Status", value: basket.status },
                  { label: "Weight basis", value: basket.weightBasis },
                  ...(liveDefinitions
                    ? [
                        {
                          label: "Performance metrics",
                          value: "Not returned by basket-definition API",
                        },
                      ]
                    : [
                        { label: "Ending balance", value: formatCompact(basket.metrics.balance, "$m") },
                        {
                          label: "Loss rate",
                          value:
                            basket.metrics.lossRate === null
                              ? "N/A"
                              : `${basket.metrics.lossRate.toFixed(2)}%`,
                        },
                        { label: "Expected profit", value: formatCompact(basket.metrics.expectedProfit, "$m") },
                      ]),
                ],
                caveat:
                  "Dynamic baskets refresh with source data. Frozen versions preserve exact members for reproducibility.",
                action: "Clone to create a controlled new version before changing an approved basket.",
              })
            }
          >
            <header>
              <span className="basket-type">{basket.type}</span>
              <StatusChip
                status={basket.approved ? "Stable" : "Watch"}
                compact
              />
            </header>
            <h3>{basket.name}</h3>
            <p>{basket.definition}</p>
            <dl>
              <div><dt>Members</dt><dd>{basket.memberCount.toLocaleString()}</dd></div>
              <div><dt>Version</dt><dd>{basket.version}</dd></div>
              <div><dt>Loss</dt><dd>{liveDefinitions || basket.metrics.lossRate === null ? "N/A" : `${basket.metrics.lossRate.toFixed(2)}%`}</dd></div>
              <div><dt>Profit</dt><dd>{liveDefinitions ? "N/A" : formatCompact(basket.metrics.expectedProfit, "$m")}</dd></div>
            </dl>
            <footer>
              <span>{basket.owner}</span>
              <span>{basket.updated} ↗</span>
            </footer>
          </button>
        ))}
      </section>
      <div className="content-grid cols-7-5">
        <Panel
          eyebrow="Set-operation composer"
          title="Create a reproducible combined population"
          subtitle="Preview membership before saving a new version"
        >
          <div className="set-composer">
            <label>
              <span>Basket A</span>
              <select value={leftId} onChange={(event) => setLeftId(event.target.value)}>
                {data.baskets.map((basket) => (
                  <option value={basket.id} key={basket.id}>{basket.name}</option>
                ))}
              </select>
            </label>
            <SegmentedControl
              label="Set operation"
              value={operation}
              options={[
                { value: "union", label: "Union" },
                { value: "intersect", label: "Intersect" },
                { value: "except", label: "Except" },
              ]}
              onChange={setOperation}
            />
            <label>
              <span>Basket B</span>
              <select value={rightId} onChange={(event) => setRightId(event.target.value)}>
                {data.baskets.map((basket) => (
                  <option value={basket.id} key={basket.id}>{basket.name}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="set-preview">
            <div>
              <span>Preview population</span>
              <strong>
                {liveDefinitions
                  ? "Not calculated"
                  : estimatedMembers.toLocaleString()}
              </strong>
              <small>
                {liveDefinitions
                  ? "illustrative UI overlap estimate; not API output"
                  : "entities at account-month grain"}
              </small>
            </div>
            <div>
              <span>Estimated balance</span>
              <strong>
                {liveDefinitions
                  ? "Not calculated"
                  : formatCompact(
                      (left?.metrics.balance ?? 0) *
                        (operation === "intersect" ? 0.31 : 0.77),
                      "$m",
                    )}
              </strong>
              <small>
                {liveDefinitions
                  ? "definition endpoint has no performance aggregate"
                  : "ending balance weight"}
              </small>
            </div>
            <div>
              <span>Definition status</span>
              <strong>Draft v1</strong>
              <small>impact preview only</small>
            </div>
            <small className="read-only-note">
              Read-only preview. Persist definitions through the versioned basket API.
            </small>
          </div>
        </Panel>
        <Panel
          eyebrow="Cross-domain lineage"
          title="How the group connects"
          subtitle="Selected analytical grain prevents double counting"
        >
          <div className="lineage-stack">
            {[
              "Customer",
              "Account",
              "Product",
              "Membership tier",
              "Benefit usage",
              "Partner",
              "Vendor",
              "Strategy",
              "Region",
            ].map((step, index) => (
              <div key={step}>
                <span>{index + 1}</span>
                <strong>{step}</strong>
                {index < 8 ? <i aria-hidden="true">↓</i> : null}
              </div>
            ))}
          </div>
        </Panel>
      </div>
      <Panel
        eyebrow={liveDefinitions ? "Versioned demo workspace templates" : "Workspace templates"}
        title="Reusable analysis starts"
        subtitle="Configuration, notes, commentary and export settings reopen together"
      >
        <div className="template-grid">
          {[
            ["Monthly Portfolio Review", "KPI movement · root cause · commentary", "Executive"],
            ["Weekly Emerging-Risk Review", "Alerts · persistence · owners", "Risk"],
            ["Partner Performance Review", "Economics · rating · scenario", "Partner"],
            ["Vendor Oversight Review", "Quality · capacity · exit readiness", "Vendor"],
            ["Vintage Deterioration Investigation", "Maturity · cohorts · decomposition", "Credit"],
            ["Forecast and Stress Review", "Assumptions · projections · variance", "Finance"],
          ].map(([title, detail, tag]) => (
            <article key={title}>
              <span>{tag}</span>
              <strong>{title}</strong>
              <small>{detail}</small>
            </article>
          ))}
        </div>
      </Panel>
    </>
  );
}

export function FinancePage(props: PageProps) {
  const { data, mode, onOpenEvidence } = props;
  const current = data.finance.bridge.find((item) => item.group === "closing");
  const prior = data.finance.bridge.find((item) => item.group === "opening");
  const variance = (current?.value ?? 0) - (prior?.value ?? 0);
  const partnerHhi =
    data.finance.concentration.find((item) =>
      item.label.includes("partner transaction hhi"),
    )?.value ?? 0;
  const vendorHhi =
    data.finance.concentration.find((item) =>
      item.label.includes("vendor volume hhi"),
    )?.value ?? 0;
  return (
    <>
      <PageHeader
        eyebrow="Finance analytics studio"
        title="Follow expected profit back to its operating drivers."
        summary="A transparent finance bridge connects growth, pricing assumptions, credit, fraud, partners, vendors, benefits and customer friction."
        facts={[
          {
            label: "Current expected profit",
            value: formatCompact(current?.value, "$m"),
            status: variance >= 0 ? "Favourable" : "Adverse",
          },
          { label: "Prior period", value: formatCompact(prior?.value, "$m") },
          { label: "Variance", value: formatCompact(variance, "$m") },
        ]}
      />
      <ModeNote mode={mode} />
      <Panel
        eyebrow="Profitability bridge"
        title="Prior to current expected profit"
        subtitle="Synthetic assumption-driven portfolio-planning measure · $m"
        action={
          <MethodologyPopover title="Expected portfolio profit">
            Revenue less funding, operating, credit loss, fraud loss, review and
            customer-friction costs. Every assumption is versioned and exportable.
          </MethodologyPopover>
        }
      >
        <WaterfallChart items={data.finance.bridge} />
      </Panel>
      <div className="content-grid cols-6-6">
        <Panel
          eyebrow="Unit economics"
          title="Current versus prior period"
          subtitle="Comparable portfolio units"
        >
          <div className="unit-economics-list">
            {data.finance.unitEconomics.map((item) => {
              const change =
                item.secondary === undefined
                  ? null
                  : ((item.value - item.secondary) / Math.abs(item.secondary)) * 100;
              return (
                <button
                  type="button"
                  key={item.label}
                  onClick={() =>
                    onOpenEvidence({
                      eyebrow: "Unit economics evidence",
                      title: item.label,
                      summary: "Current and prior period values use a consistent unit denominator.",
                      facts: [
                        { label: "Current", value: `$${item.value.toFixed(0)}` },
                        {
                          label: "Prior",
                          value:
                            item.secondary === undefined
                              ? "Not returned"
                              : `$${item.secondary.toFixed(0)}`,
                        },
                        {
                          label: "Change",
                          value:
                            change === null
                              ? "Not calculated"
                              : `${change >= 0 ? "+" : ""}${change.toFixed(1)}%`,
                        },
                      ],
                      caveat:
                        "These are synthetic planning economics, not audited financial statements.",
                    })
                  }
                >
                  <span>
                    <strong>{item.label}</strong>
                    <small>
                      {item.secondary === undefined
                        ? "Current API value"
                        : `Prior $${item.secondary.toFixed(0)}`}
                    </small>
                  </span>
                  <b>${item.value.toFixed(0)}</b>
                  <i className={change !== null && change > 0 ? "is-up" : "is-down"}>
                    {change === null
                      ? "Current"
                      : `${change >= 0 ? "+" : ""}${change.toFixed(1)}%`}
                  </i>
                </button>
              );
            })}
          </div>
        </Panel>
        <Panel
          eyebrow="Dependency"
          title="Contribution concentration"
          subtitle="Share of selected measure · HHI available in evidence pack"
        >
          <HorizontalBars data={data.finance.concentration} />
          <div className="concentration-summary">
            <span><small>Partner HHI</small><strong>{partnerHhi.toFixed(0)}</strong></span>
            <span><small>Vendor HHI</small><strong>{vendorHhi.toFixed(0)}</strong></span>
            <span>
              <small>Effective vendors</small>
              <strong>
                {vendorHhi > 0 ? (10_000 / vendorHhi).toFixed(1) : "N/A"}
              </strong>
            </span>
          </div>
        </Panel>
      </div>
      <Panel
        eyebrow="Driver tree"
        title="From financial outcome to operational evidence"
        subtitle="Select any driver to inspect assumptions and source lineage"
      >
        <div className="driver-tree">
          <div className="driver-root">
            <span>Expected profit</span>
            <strong>{formatCompact(current?.value, "$m")}</strong>
          </div>
          <div className="driver-branches">
            {data.finance.driverTree
              .filter((item) => item.parent === "Expected profit")
              .map((item) => (
                <button
                  type="button"
                  key={item.child}
                  className={item.value >= 0 ? "is-positive" : "is-negative"}
                  onClick={() =>
                    onOpenEvidence({
                      eyebrow: "Finance driver evidence",
                      title: item.child,
                      summary: `${item.child} contributes ${formatCompact(item.value, "$m")} to the synthetic expected-profit equation.`,
                      facts: [
                        { label: "Contribution", value: formatCompact(item.value, "$m") },
                        { label: "Parent", value: item.parent },
                        { label: "Calculation version", value: data.metadata.calculationVersion },
                      ],
                      caveat:
                        "Risk charges are internal analytical analogues, not regulatory capital measures.",
                    })
                  }
                >
                  <span>{item.child}</span>
                  <strong>{formatCompact(item.value, "$m")}</strong>
                  <i aria-hidden="true">↗</i>
                </button>
              ))}
          </div>
        </div>
      </Panel>
    </>
  );
}

export function DataQualityPage(props: PageProps) {
  const { data, mode, onOpenEvidence } = props;
  const failures = data.dataQuality.checks.filter((check) => check.status === "Fail");
  const warnings = data.dataQuality.checks.filter((check) => check.status === "Warning");
  const affectedRows = data.dataQuality.checks.reduce(
    (sum, check) => sum + check.affectedRows,
    0,
  );
  const qualitySignal =
    failures.length > 0
      ? "Critical"
      : warnings.length > 0
        ? "Watch"
        : "Favourable";
  return (
    <>
      <PageHeader
        eyebrow="Data quality and lineage"
        title={
          failures.length > 0
            ? `${failures.length} publication failure${failures.length === 1 ? "" : "s"} require remediation.`
            : warnings.length > 0
              ? `No critical failure. ${warnings.length} warning${warnings.length === 1 ? "" : "s"} remain visible.`
              : "All returned publication checks passed."
        }
        summary="Metrics publish only after schema, key, business-rule, reconciliation, freshness and completeness controls pass."
        facts={[
          {
            label: "Quality score",
            value: `${data.dataQuality.score.toFixed(1)} / 100`,
            status: qualitySignal,
          },
          { label: "Critical failures", value: failures.length.toString() },
          { label: "Warnings", value: warnings.length.toString() },
        ]}
      />
      <ModeNote mode={mode} />
      <div className="quality-hero">
        <div className="quality-ring">
          <span>{data.dataQuality.score.toFixed(1)}</span>
          <small>quality score</small>
        </div>
        <div className="quality-hero-copy">
          <StatusChip status={qualitySignal} />
          <h2>{data.dataQuality.status.replaceAll("_", " ")}</h2>
          <p>
            {affectedRows > 0
              ? `${affectedRows.toLocaleString()} affected observations are disclosed by the returned checks.`
              : "No affected rows were reported by the returned checks."}{" "}
            Publication follows the current run&apos;s explicit quality gate.
          </p>
        </div>
        <div className="quality-counts">
          <span><strong>{data.dataQuality.checks.filter((check) => check.status === "Pass").length}</strong><small>Passed</small></span>
          <span><strong>{warnings.length}</strong><small>Warnings</small></span>
          <span><strong>{failures.length}</strong><small>Failed</small></span>
        </div>
      </div>
      <Panel
        eyebrow="Publication checks"
        title="Controls and business impact"
        subtitle="Select a check for affected rows, quarantine and corrective action"
      >
        <TableShell label="Data quality control results">
          <table className="data-table quality-table">
            <thead>
              <tr>
                <th>Check</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Affected rows</th>
                <th>Business impact</th>
                <th>Corrective recommendation</th>
              </tr>
            </thead>
            <tbody>
              {data.dataQuality.checks.map((check) => (
                <tr
                  key={check.id}
                  onClick={() =>
                    onOpenEvidence({
                      eyebrow: `Data-quality check · ${check.id}`,
                      title: check.name,
                      summary: check.businessImpact,
                      facts: [
                        { label: "Severity", value: check.severity },
                        { label: "Status", value: check.status },
                        { label: "Affected rows", value: check.affectedRows.toLocaleString() },
                        { label: "Quarantine", value: check.quarantine },
                        { label: "Recommendation", value: check.recommendation },
                      ],
                      caveat:
                        check.status === "Warning"
                          ? "The warning is disclosed and assessed for KPI materiality before publication."
                          : "This check passed for the current run.",
                    })
                  }
                >
                  <th scope="row"><span>{check.id}</span>{check.name}</th>
                  <td>{check.severity}</td>
                  <td>
                    <StatusChip
                      status={
                        check.status === "Pass"
                          ? "Favourable"
                          : check.status === "Fail"
                            ? "Critical"
                            : "Watch"
                      }
                      compact
                    />
                  </td>
                  <td>{check.affectedRows.toLocaleString()}</td>
                  <td>{check.businessImpact}</td>
                  <td>{check.recommendation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableShell>
      </Panel>
      <div className="content-grid cols-5-7">
        <Panel
          eyebrow="Run manifest"
          title={data.metadata.runId}
          subtitle="Deterministic generation and validation record"
        >
          <dl className="manifest-grid">
            {data.dataQuality.manifest.map((item) => (
              <div key={item.label}>
                <dt>{item.label}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
        </Panel>
        <Panel
          eyebrow="End-to-end lineage"
          title="Every executive number is traceable"
          subtitle="Source → transformation → API → interface → export"
        >
          <div className="lineage-flow">
            {data.dataQuality.lineage.map((step, index) => (
              <div key={step}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{step}</strong>
                {index < data.dataQuality.lineage.length - 1 ? (
                  <i aria-hidden="true">→</i>
                ) : null}
              </div>
            ))}
          </div>
          <div className="lineage-meta">
            <span><small>Calculation registry</small><strong>{data.metadata.calculationVersion}</strong></span>
            <span><small>Run</small><strong>{data.metadata.runId}</strong></span>
            <span><small>API contract</small><strong>v1</strong></span>
            <span><small>Export reconciliation</small><strong>Validate in generated package</strong></span>
          </div>
        </Panel>
      </div>
    </>
  );
}

export function ForecastPage(props: PageProps) {
  const { data, mode, onOpenEvidence } = props;
  const [scenarioId, setScenarioId] = useState("mild");
  const scenario =
    data.scenarios.find((item) => item.id === scenarioId) ??
    data.scenarios.find((item) => item.name === "Mild Downturn") ??
    data.scenarios[0];
  const baseline =
    data.scenarios.find((item) => item.id === "baseline") ?? data.scenarios[0];
  if (!scenario || !baseline) {
    return (
      <DataState
        type="empty"
        title="No scenario results for this scope"
        detail="Choose a broader reporting scope or verify that the scenario service returned governed projections."
      />
    );
  }
  const adjustedPoints = scenario.projections.map((point) => ({
    month: point.month,
    value: point.annualisedLossRate,
  }));
  return (
    <>
      <PageHeader
        eyebrow="Forecast and stress lab"
        title="Transparent scenarios, editable assumptions."
        summary="Twelve-month portfolio-planning projections expose transmission logic, intervals and differences from baseline."
        facts={[
          { label: "Selected scenario", value: scenario.name, status: scenario.id === "baseline" ? "Stable" : "Watch" },
          { label: "Horizon", value: "12 months" },
          { label: "Regulatory status", value: "Not a regulatory scenario" },
        ]}
      />
      <ModeNote mode={mode} />
      <div className="scenario-tabs" role="tablist" aria-label="Scenario selection">
        {data.scenarios.map((item) => (
          <button
            type="button"
            role="tab"
            aria-selected={item.id === scenario.id}
            className={item.id === scenario.id ? "is-active" : ""}
            key={item.id}
            onClick={() => setScenarioId(item.id)}
          >
            <span>{item.name}</span>
            <small>
              {item.deltaFromBaseline === 0
                ? "Reference"
                : `${formatCompact(item.deltaFromBaseline, "$m")} vs baseline`}
            </small>
          </button>
        ))}
      </div>
      <div className="content-grid cols-8-4">
        <Panel
          eyebrow="Twelve-month projection"
          title="Annualised net loss rate"
          subtitle={`${scenario.name} · governed portfolio-planning estimate`}
          action={<StatusChip status={scenario.id === "baseline" ? "Stable" : "Watch"} compact />}
        >
          <ChartInteractionFrame
            label={`${scenario.name} annualised net loss rate`}
            filename="naim-scenario-comparison.csv"
            rows={({ range }) => {
              const count = Number(range);
              return scenario.projections.slice(-count).map((point, index) => {
                const baselinePoint = baseline.projections.slice(-count)[index];
                return {
                  month: point.month,
                  selected_scenario: scenario.name,
                  selected_loss_rate_percent: point.annualisedLossRate,
                  baseline_loss_rate_percent: baselinePoint?.annualisedLossRate ?? null,
                  selected_expected_profit_usd_m: scenario.expectedProfit,
                  baseline_expected_profit_usd_m: baseline.expectedProfit,
                };
              });
            }}
            rangeOptions={[
              { value: "6", label: "6M" },
              { value: "12", label: "12M" },
            ]}
            defaultRange="12"
            onOpenEvidence={() =>
              onOpenEvidence({
                eyebrow: "Scenario evidence",
                title: `${scenario.name} versus ${baseline.name}`,
                summary: scenario.description,
                facts: [
                  { label: "Cumulative loss", value: formatCompact(scenario.cumulativeLoss, "$m") },
                  { label: "Expected profit", value: formatCompact(scenario.expectedProfit, "$m") },
                  { label: "Delta from baseline", value: formatCompact(scenario.deltaFromBaseline, "$m") },
                  { label: "Consumer stress", value: scenario.assumptions.consumerStress.toFixed(0) },
                ],
                caveat: "This is an assumption-driven portfolio-planning scenario, not a regulatory forecast.",
              })
            }
          >
            {({ range }) => (
              <TrendBars
                points={adjustedPoints.slice(-Number(range))}
                unit="%"
                label={`${scenario.name} annualised net loss rate`}
              />
            )}
          </ChartInteractionFrame>
          <div className="forecast-summary">
            <span>
              <small>Ending loss rate</small>
              <strong>{adjustedPoints.at(-1)?.value.toFixed(2)}%</strong>
            </span>
            <span>
              <small>Cumulative credit loss</small>
              <strong>{formatCompact(scenario.cumulativeLoss, "$m")}</strong>
            </span>
            <span>
              <small>Cumulative fraud</small>
              <strong>{formatCompact(scenario.cumulativeFraud, "$m")}</strong>
            </span>
            <span>
              <small>Expected profit</small>
              <strong>{formatCompact(scenario.expectedProfit, "$m")}</strong>
            </span>
          </div>
        </Panel>
        <Panel
          eyebrow="Versioned assumptions"
          title={scenario.name}
          subtitle={scenario.description}
          className="assumption-panel"
        >
          {[
            ["Consumer stress index", scenario.assumptions.consumerStress, 80, 160, ""],
            ["Unemployment", scenario.assumptions.unemployment, 3, 9, "%"],
            ["Interest rate", scenario.assumptions.interestRate, 2, 7, "%"],
            ["Fraud pressure index", scenario.assumptions.fraudPressure, 80, 170, ""],
          ].map(([label, value, min, max, suffix], index) => (
            <label className="range-control" key={String(label)}>
              <span>
                <strong>{String(label)}</strong>
                <b>
                  {Number(value).toFixed(index > 0 && index < 3 ? 1 : 0)}
                  {String(suffix)}
                </b>
              </span>
              <input
                type="range"
                min={Number(min)}
                max={Number(max)}
                step={index > 0 && index < 3 ? 0.1 : 1}
                value={Number(value)}
                disabled
                title="Choose a versioned scenario tab to change assumptions."
              />
            </label>
          ))}
          <p className="comparison-note">
            Custom assumption runs are available through the validated
            <code> /scenarios/run </code> API; this view displays saved scenario
            definitions without client-side recalculation.
          </p>
        </Panel>
      </div>
      <Panel
        eyebrow="Scenario comparison"
        title="Portfolio planning outcomes"
        subtitle="Cumulative 12-month results versus baseline"
      >
        <TableShell label="Scenario outcome comparison">
          <table className="data-table scenario-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Consumer stress</th>
                <th>Unemployment</th>
                <th>Fraud pressure</th>
                <th>Cumulative loss</th>
                <th>Cumulative fraud</th>
                <th>Expected profit</th>
                <th>Delta from baseline</th>
              </tr>
            </thead>
            <tbody>
              {data.scenarios.map((row) => (
                <tr
                  key={row.id}
                  className={row.id === scenario.id ? "is-selected" : ""}
                  onClick={() => setScenarioId(row.id)}
                >
                  <th scope="row">{row.name}<small>{row.description}</small></th>
                  <td>{row.assumptions.consumerStress}</td>
                  <td>{row.assumptions.unemployment.toFixed(1)}%</td>
                  <td>{row.assumptions.fraudPressure}</td>
                  <td>{formatCompact(row.cumulativeLoss, "$m")}</td>
                  <td>{formatCompact(row.cumulativeFraud, "$m")}</td>
                  <td>{formatCompact(row.expectedProfit, "$m")}</td>
                  <td>
                    <StatusChip
                      status={row.deltaFromBaseline < -10 ? "Adverse" : row.deltaFromBaseline < 0 ? "Watch" : "Stable"}
                      compact
                    />
                    {formatCompact(row.deltaFromBaseline, "$m")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableShell>
      </Panel>
      <Panel
        eyebrow="Transmission logic"
        title="How assumptions reach portfolio outputs"
        subtitle="Configured elasticities; no hidden scenario mechanics"
      >
        <div className="transmission-grid">
          {[
            ["Consumer stress", "Missed-payment probability", "Delinquency transitions", "Credit loss"],
            ["Unemployment", "Payment capacity", "Roll-forward rates", "Charge-offs"],
            ["Interest rate", "Funding cost", "Net contribution", "Expected profit"],
            ["Fraud pressure", "Alerts + confirmed events", "Review workload", "Fraud loss + friction"],
          ].map((path) => (
            <button
              type="button"
              key={path[0]}
              onClick={() =>
                onOpenEvidence({
                  eyebrow: "Scenario transmission",
                  title: path[0],
                  summary: path.join(" → "),
                  facts: [
                    { label: "Method", value: "Transparent state projection with configured elasticities" },
                    { label: "Reference", value: "Latest-state persistence baseline" },
                    { label: "Uncertainty", value: "Illustrative net-credit-loss interval" },
                  ],
                  caveat:
                    "Scenario transmission is an assumption-driven planning model, not a regulatory capital forecast.",
                })
              }
            >
              {path.map((step, index) => (
                <span key={step}>
                  {step}
                  {index < path.length - 1 ? <i aria-hidden="true">→</i> : null}
                </span>
              ))}
            </button>
          ))}
        </div>
      </Panel>
      <div className="comparison-note">
        <strong>Validation boundary</strong>
        <span>Planning scenario, not a regulatory forecast</span>
        <span>Assumption-driven elasticities</span>
        <span>No rolling-origin RMSE claim</span>
        <StatusChip status="Watch" compact />
      </div>
      <span className="sr-only">
        Baseline expected profit is {baseline.expectedProfit.toFixed(1)} million.
      </span>
    </>
  );
}

export function InvestigationsPage(props: PageProps) {
  const { data, mode, onOpenEvidence } = props;
  const [tab, setTab] = useState<"alerts" | "queue">("queue");
  const [createdItems, setCreatedItems] = useState<InvestigationRecord[]>([]);
  const [creating, setCreating] = useState(false);
  const investigations = [...createdItems, ...data.investigations];
  const statuses = [
    "New",
    "Assigned",
    "Investigating",
    "Action Proposed",
    "Monitoring",
    "Resolved",
  ];
  const slaAtRisk = investigations.filter(
    (item) =>
      !["Resolved", "Closed as Noise"].includes(item.status) &&
      /remaining|due|risk/i.test(item.sla),
  ).length;
  return (
    <>
      <PageHeader
        eyebrow="Early-warning centre"
        title="Every alert needs evidence, ownership and closure."
        summary="Materiality, configured noise-control metadata and evidence ownership feed an auditable investigation workflow."
        facts={[
          { label: "Open investigations", value: investigations.filter((item) => !["Resolved", "Closed as Noise"].includes(item.status)).length.toString() },
          { label: "Critical alerts", value: data.alerts.filter((alert) => alert.severity === "Critical").length.toString(), status: "Critical" },
          {
            label: "SLA requiring attention",
            value: slaAtRisk.toString(),
            status: slaAtRisk > 0 ? "Watch" : "Stable",
          },
        ]}
        actions={
          <button
            type="button"
            className="primary-button"
            disabled={creating}
            onClick={async () => {
              setCreating(true);
              try {
                const row = await createInvestigation({
                  alertId: data.alerts[0]?.id,
                  businessQuestion:
                    "What explains the selected portfolio-risk signal?",
                  affectedMetric: data.rootCause.finding.metricId,
                  hypothesis:
                    "Review the governed decomposition and maturity-aligned evidence.",
                  owner: "Portfolio Analytics",
                });
                setCreatedItems((current) => [
                  {
                    id:
                      typeof row.investigation_id === "string"
                        ? row.investigation_id
                        : `INV-${Date.now()}`,
                    alertId:
                      typeof row.alert_id === "string"
                        ? row.alert_id
                        : data.alerts[0]?.id ?? "No linked alert",
                    title: "Selected portfolio-risk signal",
                    status:
                      typeof row.status === "string" ? row.status : "New",
                    severity: "Watch",
                    owner:
                      typeof row.owner === "string"
                        ? row.owner
                        : "Portfolio Analytics",
                    opened:
                      typeof row.opened_timestamp === "string"
                        ? row.opened_timestamp
                        : "Created now",
                    sla: "SLA not assigned",
                    hypothesis:
                      typeof row.hypothesis === "string"
                        ? row.hypothesis
                        : "Review the governed evidence.",
                    evidenceCount: 0,
                    nextAction: "Record the next analytical action",
                  },
                  ...current,
                ]);
              } catch (error) {
                onOpenEvidence({
                  eyebrow: "Investigation service",
                  title: "Investigation was not created",
                  summary:
                    error instanceof Error
                      ? error.message
                      : "The API returned an unknown error.",
                  facts: [
                    { label: "Run ID", value: data.metadata.runId },
                  ],
                });
              } finally {
                setCreating(false);
              }
            }}
          >
            <span aria-hidden="true">＋</span>{" "}
            {creating ? "Creating…" : "New investigation"}
          </button>
        }
      />
      <ModeNote mode={mode} />
      <SegmentedControl
        label="Early warning view"
        value={tab}
        options={[
          { value: "queue", label: "Investigation queue" },
          { value: "alerts", label: "Alert evidence" },
        ]}
        onChange={setTab}
      />
      {tab === "alerts" ? (
        <Panel
          eyebrow="Generated alerts"
          title="Active evidence signals"
          subtitle="Rule metadata included; stateful cross-run suppression is a documented extension"
        >
          <div className="alert-evidence-grid">
            {data.alerts.map((alert) => (
              <button
                type="button"
                key={alert.id}
                onClick={() => onOpenEvidence(alertEvidence(alert))}
              >
                <header>
                  <span>{alert.id}</span>
                  <StatusChip status={alert.severity} compact />
                </header>
                <h3>{alert.title}</h3>
                <p>{alert.segment}</p>
                <dl>
                  <div><dt>Current</dt><dd>{alert.current}</dd></div>
                  <div><dt>Baseline</dt><dd>{alert.baseline}</dd></div>
                  <div><dt>Rule</dt><dd>{alert.threshold}</dd></div>
                </dl>
                <footer>
                  <span>{alert.owner}</span>
                  <span>{alert.state} · {alert.age}</span>
                </footer>
              </button>
            ))}
          </div>
        </Panel>
      ) : (
        <>
          <div className="kanban-board" aria-label="Investigation workflow board">
            {statuses.slice(0, mode === "executive" ? 4 : 6).map((statusName) => {
              const items = investigations.filter(
                (item) => item.status === statusName,
              );
              return (
                <section className="kanban-column" key={statusName}>
                  <header>
                    <span>{statusName}</span>
                    <b>{items.length}</b>
                  </header>
                  <div>
                    {items.length === 0 ? (
                      <p className="kanban-empty">No items</p>
                    ) : (
                      items.map((item) => (
                        <button
                          type="button"
                          className="kanban-card"
                          key={item.id}
                          onClick={() =>
                            onOpenEvidence({
                              eyebrow: `Investigation · ${item.id}`,
                              title: item.title,
                              summary: item.hypothesis,
                              facts: [
                                { label: "Alert", value: item.alertId },
                                { label: "Owner", value: item.owner },
                                { label: "Opened", value: item.opened },
                                { label: "SLA", value: item.sla },
                                { label: "Evidence items", value: item.evidenceCount.toString() },
                                { label: "Next action", value: item.nextAction },
                              ],
                              caveat:
                                "Investigation status and notes are synthetic and maintained for workflow demonstration.",
                              action: item.nextAction,
                            })
                          }
                        >
                          <div>
                            <span>{item.id}</span>
                            <StatusChip status={item.severity} compact />
                          </div>
                          <strong>{item.title}</strong>
                          <p>{item.hypothesis}</p>
                          <footer>
                            <span>{item.owner}</span>
                            <span>{item.sla}</span>
                          </footer>
                        </button>
                      ))
                    )}
                  </div>
                </section>
              );
            })}
          </div>
          <Panel
            eyebrow="Workflow scope"
            title="Current in-process investigation state"
            subtitle="Latest durable investigation state; alert-linked audit history is reviewed in Early Warning"
          >
            <div className="audit-timeline">
              {investigations.slice(0, 5).map((item) => (
                <div key={item.id}>
                  <span>{item.opened}</span>
                  <i aria-hidden="true" />
                  <p><strong>{item.owner}</strong>{item.status}</p>
                  <b>{item.id}</b>
                </div>
              ))}
              {investigations.length === 0 ? (
                <DataState
                  type="empty"
                  title="No current workflow records"
                  detail="Create an investigation to exercise the validated in-process API workflow."
                />
              ) : null}
            </div>
          </Panel>
        </>
      )}
    </>
  );
}

export function MethodologyPage(props: PageProps) {
  const { data, mode, onOpenEvidence } = props;
  const [section, setSection] = useState("metrics");
  const sections = [
    ["metrics", "Metric registry"],
    ["models", "Models & drift"],
    ["commentary", "Controlled commentary"],
    ["exports", "Interoperability"],
  ];
  return (
    <>
      <PageHeader
        eyebrow="Methodology and governance"
        title="Definitions, assumptions and controls travel with the result."
        summary="nAIM is a governed analytical layer for reproducible portfolio work—not a replacement for Excel, Power BI, Tableau, SAS or SQL."
        facts={[
          { label: "Metric registry", value: data.metadata.calculationVersion },
          { label: "Model artefacts", value: "Explicit versioning" },
          { label: "Commentary provider", value: data.commentary.provider },
        ]}
      />
      <ModeNote mode={mode} />
      <div className="methodology-layout">
        <nav aria-label="Methodology sections">
          {sections.map(([id, label]) => (
            <button
              type="button"
              key={id}
              className={section === id ? "is-active" : ""}
              onClick={() => setSection(id)}
            >
              {label}
              <span aria-hidden="true">→</span>
            </button>
          ))}
        </nav>
        <div className="methodology-content">
          {section === "metrics" ? (
            <>
              <Panel
                eyebrow="Metric registry"
                title="Published portfolio measures"
                subtitle="Business definition, formula, denominator, exclusions and source"
              >
                <div className="metric-registry">
                  {data.kpis.map((item) => (
                    <button type="button" key={item.id} onClick={() => onOpenEvidence(buildMetricEvidence(item))}>
                      <span>{item.id}</span>
                      <strong>{item.name}</strong>
                      <p>{item.definition.formula}</p>
                      <small>
                        {item.definition.version} · {metricLineageAvailable(item)
                          ? item.lineage?.source
                          : "LINEAGE UNAVAILABLE"}
                      </small>
                    </button>
                  ))}
                </div>
              </Panel>
            </>
          ) : null}
          {section === "models" ? (
            <Panel
              eyebrow="Model and population monitoring"
              title="Current validation evidence"
              subtitle="Temporal testing · baseline comparison · explicit approved use"
            >
              <div className="model-monitor-grid">
                {data.modelMonitoring.map((item) => (
                  <div key={item.metric}>
                    <StatusChip status={item.status} compact />
                    <span>{item.metric}</span>
                    <strong>{item.current.toFixed(item.current < 1 ? 3 : 2)}{item.unit}</strong>
                    <small>Reference {item.reference.toFixed(item.reference < 1 ? 3 : 2)}{item.unit}</small>
                    <p>{item.note}</p>
                  </div>
                ))}
              </div>
              <div className="model-card-summary">
                <div><span>Use case</span><strong>Next-month 30+ delinquency risk</strong></div>
                <div><span>Approved use</span><strong>Portfolio monitoring and explanation</strong></div>
                <div><span>Prohibited use</span><strong>Automated customer-level adverse action</strong></div>
                <div><span>Test split</span><strong>Time-based train / validation / test</strong></div>
                <div><span>Baseline</span><strong>Logistic regression</strong></div>
                <div><span>Challenger</span><strong>Histogram gradient boosting</strong></div>
              </div>
            </Panel>
          ) : null}
          {section === "commentary" ? (
            <Panel
              eyebrow="Controlled commentary"
              title="Validated evidence in; reviewable draft out"
              subtitle="No raw account records and no metric calculation by a language model"
            >
              <div className="commentary-contract">
                <div className="contract-column">
                  <span>Allowlisted evidence</span>
                  {["Reporting periods", "Validated metric values", "Root-cause contributions", "Statistical confidence", "Caveats", "Investigation steps"].map((item) => (
                    <p key={item}>✓ {item}</p>
                  ))}
                </div>
                <div className="contract-arrow">
                  <strong>{data.commentary.provider}</strong>
                  <span>Numerical verifier</span>
                  <i aria-hidden="true">→</i>
                </div>
                <div className="contract-column is-output">
                  <span>Governed output</span>
                  {["Structured narrative", "Metric IDs attached", "Unsupported numbers rejected", "Provider and prompt logged", "Human review required"].map((item) => (
                    <p key={item}>✓ {item}</p>
                  ))}
                </div>
              </div>
              <div className="commentary-preview">
                <header>
                  <span>Executive commentary</span>
                  <StatusChip status="Watch" compact />
                  <small>{data.commentary.status}</small>
                </header>
                {data.commentary.sections.map((item) => (
                  <section key={item.title}>
                    <h3>{item.title}</h3>
                    <p>{item.body}</p>
                    {item.metricIds.length > 0 ? (
                      <small>{item.metricIds.join(" · ")}</small>
                    ) : null}
                  </section>
                ))}
              </div>
            </Panel>
          ) : null}
          {section === "exports" ? (
            <Panel
              eyebrow="Interoperability"
              title="Governed results, ready for the tools teams already use"
              subtitle="Reconciliation totals and metadata travel with every package"
            >
              <div className="export-grid">
                {[
                  ["Excel MIS", "13 formatted sheets", "XLSX"],
                  ["Power BI package", "Star schema + DAX + relationships", "PARQUET"],
                  ["Tableau extract", "Documented curated tables", "CSV"],
                  ["SQL marts", "Versioned metric-ready views", "SQL"],
                  ["Evidence pack", "Findings + lineage + caveats", "JSON"],
                  ["Scenario assumptions", "Editable planning inputs", "XLSX"],
                ].map(([title, detail, type]) => (
                  <article key={title}>
                    <span>{type}</span>
                    <strong>{title}</strong>
                    <p>{detail}</p>
                    <small>Validated through the release package workflow</small>
                  </article>
                ))}
              </div>
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}

export function AlertsPage(props: PageProps) {
  const { data, mode, filters, onOpenEvidence, onNavigate, onAlertUpdated } = props;
  const apiBacked =
    isApiBacked(data) ||
    (data.metadata.dataMode === "DEMO" &&
      data.alerts.some((alert) => alert.durable && alert.lifecycle));
  const activeAlerts = activeAlertQueue(data.alerts);
  const historicalAlerts = alertHistory(data.alerts);
  const [queueView, setQueueView] = useState<"active" | "history">("active");
  const visibleAlerts = queueView === "active" ? activeAlerts : historicalAlerts;
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const selectedAlert =
    visibleAlerts.find((alert) => alert.id === selectedAlertId) ??
    visibleAlerts[0] ??
    null;
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [suppressionUntilPeriod, setSuppressionUntilPeriod] = useState("");
  const [mutation, dispatchMutation] = useReducer(alertMutationReducer, {
    phase: "idle",
  });
  const lifecycle = selectedAlert?.lifecycle;
  const pending =
    mutation.phase === "pending" && mutation.alertId === selectedAlert?.id;
  const allowedTransitions = lifecycle?.allowedTransitions.filter(
    (target) => target !== "ACKNOWLEDGED",
  ) ?? [];
  const severityCounts = ["Critical", "Adverse", "Watch", "Stable"].map(
    (severity) => ({
      severity,
      count: activeAlerts.filter((alert) => alert.severity === severity).length,
    }),
  );
  const alertTrend = (() => {
    if (!selectedAlert) return { points: [], threshold: undefined, unit: "" };
    const baseline = numberFromDisplay(selectedAlert.baseline);
    const current = numberFromDisplay(selectedAlert.current);
    const threshold = numberFromDisplay(selectedAlert.threshold);
    const unit = selectedAlert.current.includes("%")
      ? "%"
      : selectedAlert.current.toLowerCase().includes("bps")
        ? "bps"
        : "";
    return {
      points:
        baseline === null || current === null
          ? []
          : [
              { month: "Baseline", value: baseline },
              { month: "Current", value: current },
            ],
      threshold: threshold ?? undefined,
      unit,
    };
  })();

  const acknowledge = async () => {
    if (!selectedAlert || !lifecycle || !apiBacked) return;
    if (!note.trim()) {
      dispatchMutation({
        type: "failed",
        alertId: selectedAlert.id,
        mutation: "ACKNOWLEDGE",
        message: "Enter an acknowledgement note before submitting.",
      });
      return;
    }
    dispatchMutation({
      type: "begin",
      alertId: selectedAlert.id,
      mutation: "ACKNOWLEDGE",
      expectedVersion: lifecycle.version,
    });
    try {
      const refreshed = await acknowledgeDurableAlert(
        selectedAlert.id,
        lifecycle.version,
        note,
        data.metadata.dataMode,
        filters,
      );
      onAlertUpdated(refreshed);
      setNote("");
      dispatchMutation({
        type: "succeeded",
        alertId: selectedAlert.id,
        mutation: "ACKNOWLEDGE",
        version: refreshed.lifecycle?.version ?? lifecycle.version,
        message: "Acknowledgement persisted and the durable alert was refreshed.",
      });
    } catch (error) {
      dispatchMutation({
        type: "failed",
        alertId: selectedAlert.id,
        mutation: "ACKNOWLEDGE",
        message:
          error instanceof Error
            ? error.message
            : "The acknowledgement could not be persisted.",
      });
    }
  };

  const transition = async (targetStatus: AlertLifecycleTransition) => {
    if (!selectedAlert || !lifecycle || !apiBacked) return;
    if (!reason.trim()) {
      dispatchMutation({
        type: "failed",
        alertId: selectedAlert.id,
        mutation: targetStatus,
        message: "Enter a reason before submitting this transition.",
      });
      return;
    }
    dispatchMutation({
      type: "begin",
      alertId: selectedAlert.id,
      mutation: targetStatus,
      expectedVersion: lifecycle.version,
    });
    try {
      const refreshed = await transitionDurableAlert(
        selectedAlert.id,
        {
          expectedVersion: lifecycle.version,
          targetStatus,
          reason,
          suppressionUntilPeriod:
            targetStatus === "SUPPRESSED" && suppressionUntilPeriod
              ? suppressionUntilPeriod
              : undefined,
        },
        data.metadata.dataMode,
        filters,
      );
      onAlertUpdated(refreshed);
      setSelectedAlertId(refreshed.id);
      if (refreshed.lifecycle?.workflowActive === false) {
        setQueueView("history");
      }
      setReason("");
      setSuppressionUntilPeriod("");
      dispatchMutation({
        type: "succeeded",
        alertId: selectedAlert.id,
        mutation: targetStatus,
        version: refreshed.lifecycle?.version ?? lifecycle.version,
        message: `${ALERT_TRANSITION_LABELS[targetStatus]} persisted and the durable alert was refreshed.`,
      });
    } catch (error) {
      dispatchMutation({
        type: "failed",
        alertId: selectedAlert.id,
        mutation: targetStatus,
        message:
          error instanceof Error
            ? error.message
            : "The alert transition could not be persisted.",
      });
    }
  };

  const startInvestigation = async () => {
    if (!selectedAlert || !lifecycle || !apiBacked) return;
    if (lifecycle.relatedInvestigation) {
      onNavigate("investigations");
      return;
    }
    if (!lifecycle.allowedTransitions.includes("INVESTIGATING")) {
      dispatchMutation({
        type: "failed",
        alertId: selectedAlert.id,
        mutation: "START_INVESTIGATION",
        message: "The server does not currently authorize an investigation transition.",
      });
      return;
    }
    if (!reason.trim()) {
      dispatchMutation({
        type: "failed",
        alertId: selectedAlert.id,
        mutation: "START_INVESTIGATION",
        message: "Enter an investigation reason before starting the workflow.",
      });
      return;
    }
    dispatchMutation({
      type: "begin",
      alertId: selectedAlert.id,
      mutation: "START_INVESTIGATION",
      expectedVersion: lifecycle.version,
    });
    try {
      const result = await createAndLinkAlertInvestigation(
        {
          alertId: selectedAlert.id,
          expectedVersion: lifecycle.version,
          reason,
          owner: selectedAlert.owner,
        },
        data.metadata.dataMode,
        filters,
      );
      onAlertUpdated(result.alert);
      setSelectedAlertId(result.alert.id);
      setReason("");
      dispatchMutation({
        type: "succeeded",
        alertId: selectedAlert.id,
        mutation: "START_INVESTIGATION",
        version: result.alert.lifecycle?.version ?? lifecycle.version,
        message: `Investigation ${result.investigationId} is linked and the alert is investigating.`,
      });
    } catch (error) {
      dispatchMutation({
        type: "failed",
        alertId: selectedAlert.id,
        mutation: "START_INVESTIGATION",
        message:
          error instanceof Error
            ? error.message
            : "The governed investigation could not be created or linked.",
      });
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Early-warning alerts"
        title="Material signals, controlled for noise."
        summary="Thresholds, population size and explicit rule metadata convert metrics into reviewable evidence."
        facts={[
          {
            label: "Active alerts",
            value: activeAlerts.length.toString(),
            status: "Adverse",
          },
          {
            label: "Critical",
            value: activeAlerts
              .filter((alert) => alert.severity === "Critical")
              .length.toString(),
          },
          { label: "Retained history", value: historicalAlerts.length.toString() },
          { label: "Signal mix", value: earlyWarningHeadline(activeAlerts) },
        ]}
        actions={
          <button
            type="button"
            className="primary-button"
            onClick={() => onNavigate("investigations")}
          >
            Open investigation queue
          </button>
        }
      />
      <ModeNote mode={mode} />
      <div className="alert-view-switch" role="group" aria-label="Alert queue view">
        <button
          type="button"
          aria-pressed={queueView === "active"}
          onClick={() => setQueueView("active")}
        >
          Active queue ({activeAlerts.length})
        </button>
        <button
          type="button"
          aria-pressed={queueView === "history"}
          onClick={() => setQueueView("history")}
        >
          Resolved and suppressed history ({historicalAlerts.length})
        </button>
      </div>
      <section className="alert-count-strip">
        {severityCounts.map((item) => (
          <div key={item.severity}>
            <StatusChip status={item.severity} compact />
            <strong>{item.count}</strong>
            <span>active signals</span>
          </div>
        ))}
      </section>
      {selectedAlert ? (
        <Panel
          eyebrow="Selected signal movement"
          title={`${selectedAlert.metric} · ${selectedAlert.segment}`}
          subtitle="Baseline, current value and governed threshold for the selected durable signal"
          action={<StatusChip status={selectedAlert.severity} compact />}
        >
          <ChartInteractionFrame
            label={`${selectedAlert.metric} early-warning movement`}
            filename="naim-early-warning-signal.csv"
            rows={alertTrend.points.map((point) => ({
              observation: point.month,
              value: point.value,
              unit: alertTrend.unit,
              threshold: alertTrend.threshold ?? null,
              alert_id: selectedAlert.id,
              owner: selectedAlert.owner,
              status: selectedAlert.state,
              recurrence: selectedAlert.lifecycle?.recurrenceCount ?? null,
            }))}
            onOpenEvidence={() => onOpenEvidence(alertEvidence(selectedAlert))}
            onDrillThrough={() =>
              document.getElementById("alert-lifecycle")?.scrollIntoView({ behavior: "smooth" })
            }
          >
            {() => (
              <TrendBars
                points={alertTrend.points}
                unit={alertTrend.unit}
                label={`${selectedAlert.metric} baseline and current value`}
                threshold={alertTrend.threshold}
              />
            )}
          </ChartInteractionFrame>
        </Panel>
      ) : null}
      <Panel
        eyebrow="Alert evidence"
        title="Current generated signals"
        subtitle={queueView === "active"
          ? "Only server-returned workflow-active signals are counted in this queue"
          : "Terminal durable records remain available with their evidence and audit chain"}
      >
        {visibleAlerts.length === 0 ? (
          <DataState
            type="empty"
            title={queueView === "active" ? "No workflow-active alerts" : "No retained terminal alerts"}
            detail="The view reflects the durable lifecycle facts returned by the alert service."
          />
        ) : (
          <div className="alert-evidence-grid" role="list">
            {visibleAlerts.map((alert) => (
              <article
                key={alert.id}
                role="listitem"
                className={selectedAlert?.id === alert.id ? "is-selected" : ""}
              >
                <header>
                  <span>{alert.id}</span>
                  <StatusChip status={alert.severity} compact />
                </header>
                <h3>{alert.title}</h3>
                <p>{alert.segment}</p>
                <dl>
                  <div><dt>Current</dt><dd>{alert.current}</dd></div>
                  <div><dt>Baseline</dt><dd>{alert.baseline}</dd></div>
                  <div><dt>Rule</dt><dd>{alert.threshold}</dd></div>
                  {alert.lifecycle ? (
                    <>
                      <div><dt>Status</dt><dd>{lifecycleStatusLabel(alert.lifecycle.status)}</dd></div>
                      <div><dt>Recurrence</dt><dd>{alert.lifecycle.recurrenceCount}</dd></div>
                      <div><dt>SLA due</dt><dd>{alert.lifecycle.sla.dueAt}</dd></div>
                    </>
                  ) : null}
                </dl>
                <footer>
                  <span>{alert.owner}</span>
                  <span>{alert.state} · {alert.age}</span>
                </footer>
                <div className="alert-card-actions">
                  <button type="button" onClick={() => setSelectedAlertId(alert.id)}>
                    Manage lifecycle
                  </button>
                  <button type="button" onClick={() => onOpenEvidence(alertEvidence(alert))}>
                    Open evidence
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </Panel>
      <Panel
        id="alert-lifecycle"
        eyebrow="Durable lifecycle"
        title={selectedAlert ? `${selectedAlert.id} · ${selectedAlert.state}` : "Select an alert"}
        subtitle="Server-authorized actions use optimistic version checks and refresh the returned durable row"
      >
        {!selectedAlert ? (
          <DataState
            type="empty"
            title="No alert selected"
            detail="Choose an alert from the active queue or retained history."
          />
        ) : !apiBacked || selectedAlert.durable !== true || !lifecycle ? (
          <DataState
            type="empty"
            title="Durable lifecycle controls unavailable"
            detail="This alert is a local demonstration fixture. No acknowledgement, transition, audit, or persistence claim is made."
          />
        ) : (
          <div className="alert-lifecycle-layout">
            <section className="alert-lifecycle-facts" aria-labelledby="alert-lifecycle-facts-title">
              <h3 id="alert-lifecycle-facts-title">Workflow facts</h3>
              <dl>
                <div><dt>Owner</dt><dd>{selectedAlert.owner}</dd></div>
                <div><dt>Status</dt><dd>{lifecycleStatusLabel(lifecycle.status)}</dd></div>
                <div><dt>Version</dt><dd>{lifecycle.version}</dd></div>
                <div><dt>Condition active</dt><dd>{lifecycle.conditionActive ? "Yes" : "No"}</dd></div>
                <div><dt>Workflow active</dt><dd>{lifecycle.workflowActive ? "Yes" : "No"}</dd></div>
                <div><dt>Acknowledged</dt><dd>{lifecycle.acknowledgement.acknowledged ? "Yes" : "No"}</dd></div>
                <div><dt>Acknowledged by</dt><dd>{lifecycle.acknowledgement.by ?? "Not acknowledged"}</dd></div>
                <div><dt>Acknowledged at</dt><dd>{lifecycle.acknowledgement.at ?? "Not acknowledged"}</dd></div>
                <div><dt>Acknowledgement note</dt><dd>{lifecycle.acknowledgement.note ?? "Not acknowledged"}</dd></div>
                <div><dt>SLA</dt><dd>{lifecycle.sla.hours} hours · due {lifecycle.sla.dueAt}</dd></div>
                <div><dt>Recurrence count</dt><dd>{lifecycle.recurrenceCount}</dd></div>
                <div><dt>First observed</dt><dd>{lifecycle.firstObservedAt} · {lifecycle.firstObservedPeriod}</dd></div>
                <div><dt>Last observed</dt><dd>{lifecycle.lastObservedAt} · {lifecycle.lastObservedPeriod}</dd></div>
                <div><dt>Cooldown</dt><dd>{lifecycle.cooldown.periods} period(s) · until {lifecycle.cooldown.untilPeriod ?? "not set"}</dd></div>
                <div><dt>Suppression</dt><dd>{lifecycle.suppression.active ? `${lifecycle.suppression.reason ?? "Reason unavailable"} · until ${lifecycle.suppression.untilPeriod ?? "not set"}` : "Not active"}</dd></div>
                <div><dt>Resolution</dt><dd>{lifecycle.resolution.at ? `${lifecycle.resolution.reason ?? "Reason unavailable"} · ${lifecycle.resolution.at}` : "Not resolved"}</dd></div>
                <div><dt>Related investigation</dt><dd>{lifecycle.relatedInvestigation ?? "None linked"}</dd></div>
              </dl>
              <div className="alert-evidence-binding">
                <strong>Latest governed evidence</strong>
                <span>Run {lifecycle.latestEvidence.runId}</span>
                <span>Period {lifecycle.latestEvidence.period}</span>
                <span>Data quality {lifecycle.latestEvidence.dataQualityStatus}</span>
                <span>Denominator {lifecycle.latestEvidence.denominator.toLocaleString()}</span>
                <code>{lifecycle.latestEvidence.observationKey}</code>
              </div>
            </section>
            <section className="alert-lifecycle-actions" aria-labelledby="alert-lifecycle-actions-title">
              <h3 id="alert-lifecycle-actions-title">Governed actions</h3>
              {lifecycle.canAcknowledge ? (
                <fieldset disabled={pending}>
                  <legend>Acknowledge</legend>
                  <label htmlFor={`alert-note-${selectedAlert.id}`}>Required acknowledgement note</label>
                  <textarea
                    id={`alert-note-${selectedAlert.id}`}
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    required
                  />
                  <button type="button" onClick={() => void acknowledge()}>
                    {pending && mutation.phase === "pending" && mutation.mutation === "ACKNOWLEDGE"
                      ? "Acknowledging…"
                      : "Acknowledge"}
                  </button>
                </fieldset>
              ) : null}
              {allowedTransitions.length > 0 ? (
                <fieldset disabled={pending}>
                  <legend>Change workflow status</legend>
                  <label htmlFor={`alert-reason-${selectedAlert.id}`}>Required transition reason</label>
                  <textarea
                    id={`alert-reason-${selectedAlert.id}`}
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    required
                  />
                  {allowedTransitions.includes("SUPPRESSED") ? (
                    <>
                      <label htmlFor={`alert-suppression-period-${selectedAlert.id}`}>
                        Suppression until period (optional)
                      </label>
                      <input
                        id={`alert-suppression-period-${selectedAlert.id}`}
                        value={suppressionUntilPeriod}
                        onChange={(event) => setSuppressionUntilPeriod(event.target.value)}
                        placeholder="YYYY-MM"
                      />
                    </>
                  ) : null}
                  <div className="alert-transition-actions">
                    {allowedTransitions.map((target) => (
                      <button
                        type="button"
                        key={target}
                        onClick={() => void transition(target)}
                      >
                        {pending && mutation.phase === "pending" && mutation.mutation === target
                          ? `${ALERT_TRANSITION_LABELS[target]}…`
                          : ALERT_TRANSITION_LABELS[target]}
                      </button>
                    ))}
                  </div>
                </fieldset>
              ) : (
                <p>No workflow transitions are currently authorized by the server.</p>
              )}
              <button
                type="button"
                className="secondary-button"
                disabled={pending}
                onClick={() => void startInvestigation()}
              >
                {lifecycle.relatedInvestigation ? "Open related investigation" : "Start Investigation"}
              </button>
              {mutation.phase === "pending" && mutation.alertId === selectedAlert.id ? (
                <p className="alert-mutation-state tone-watch" role="status">
                  Persisting {mutation.mutation.toLowerCase().replaceAll("_", " ")}…
                </p>
              ) : null}
              {mutation.phase === "success" && mutation.alertId === selectedAlert.id ? (
                <p className="alert-mutation-state tone-favourable" role="status">
                  {mutation.message} Version {mutation.version}.
                </p>
              ) : null}
              {mutation.phase === "failure" && mutation.alertId === selectedAlert.id ? (
                <p className="alert-mutation-state tone-critical" role="alert">
                  {mutation.message} The visible durable record was not promoted.
                </p>
              ) : null}
            </section>
            <section className="alert-audit-history" aria-labelledby="alert-audit-title">
              <h3 id="alert-audit-title">Audit history</h3>
              <p>
                Integrity {lifecycle.auditIntegrity.status} · chain {lifecycle.auditIntegrity.chainValid ? "valid" : "invalid"} · {lifecycle.auditIntegrity.eventCount} event(s)
              </p>
              {lifecycle.auditEvents.length > 0 ? (
                <ol>
                  {lifecycle.auditEvents.map((event) => (
                    <li key={event.eventHash}>
                      <strong>{event.eventType.replaceAll("ALERT_", "").replaceAll("_", " ")}</strong>
                      <span>{event.occurredAt} · {event.actor}</span>
                      <code>{JSON.stringify(event.payload)}</code>
                      <small>Event hash {event.eventHash}</small>
                    </li>
                  ))}
                </ol>
              ) : (
                <p>No audit events were returned.</p>
              )}
              {lifecycle.reopenHistory.length > 0 ? (
                <details>
                  <summary>Reopen history ({lifecycle.reopenHistory.length})</summary>
                  <ol>
                    {lifecycle.reopenHistory.map((event) => (
                      <li key={`${event.observationKey}-${event.reopenedAt}`}>
                        <strong>{event.priorStatus} → NEW</strong>
                        <span>{event.reopenedAt} · {event.reason}</span>
                        <code>{event.observationKey}</code>
                      </li>
                    ))}
                  </ol>
                </details>
              ) : null}
            </section>
          </div>
        )}
      </Panel>
      <div className="content-grid cols-6-6">
        {apiBacked ? (
          <Panel
            eyebrow="Noise controls"
            title="Durable state is server governed"
            subtitle="Cooldown, suppression, recurrence and audit facts are shown only from the alert API"
          >
            <div className="control-list">
              {[
                ["Active queue", `${activeAlerts.length} workflow-active alert(s)`, "Watch"],
                ["Retained history", `${historicalAlerts.length} terminal record(s)`, "Stable"],
                ["Audit integrity", lifecycle ? `${lifecycle.auditIntegrity.status} for selected alert` : "Select an alert", lifecycle?.auditIntegrity.status === "PASS" ? "Favourable" : "Watch"],
                ["Server authorization", lifecycle ? `${lifecycle.allowedTransitions.length} transition(s) currently allowed` : "Select an alert", "Stable"],
              ].map(([title, detail, signal]) => (
                <div key={title}>
                  <span><strong>{title}</strong><small>{detail}</small></span>
                  <StatusChip status={signal} compact />
                </div>
              ))}
            </div>
          </Panel>
        ) : (
        <Panel
          eyebrow="Noise controls"
          title="Why these signals survived"
          subtitle="Configured at alert-rule level"
        >
          <div className="control-list">
            {[
              ["Minimum denominator", "All alerts exceed configured population floors", "Favourable"],
              ["Persistence", "Required-period settings are stored with each rule", "Stable"],
              ["Cooldown", "Configuration recorded; cross-run state enforcement is not yet implemented", "Watch"],
              ["Duplicate suppression", "Deterministic keys emitted; durable suppression state is not yet implemented", "Watch"],
              ["Data-quality gate", "No critical publication failure", "Watch"],
            ].map(([title, detail, signal]) => (
              <div key={title}>
                <span><strong>{title}</strong><small>{detail}</small></span>
                <StatusChip status={signal} compact />
              </div>
            ))}
          </div>
        </Panel>
        )}
        <Panel
          eyebrow="Ownership and SLA"
          title="Evidence becomes workflow"
          subtitle="No alert closes without an auditable outcome"
        >
          <div className="ownership-flow">
            {[
              ["1", "Generated", "Rule + evidence stored"],
              ["2", "Triaged", "Materiality confirmed"],
              ["3", "Assigned", "Named analytical owner"],
              ["4", "Investigated", "Hypothesis and evidence"],
              ["5", "Closed", "Resolution + reviewer"],
            ].map(([number, title, detail]) => (
              <div key={number}>
                <span>{number}</span>
                <strong>{title}</strong>
                <small>{detail}</small>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </>
  );
}

export function ModelMonitoringPage(props: PageProps) {
  const { data, mode, onOpenEvidence } = props;
  const modelName =
    data.filterOptions.modelVersions.find((item) => !item.startsWith("All ")) ??
    "Population drift monitor";
  const monitoringSignal = data.modelMonitoring.some(
    (item) => item.status === "Critical" || item.status === "Adverse",
  )
    ? "Adverse"
    : data.modelMonitoring.some((item) => item.status === "Watch")
      ? "Watch"
      : "Stable";
  return (
    <>
      <PageHeader
        eyebrow="Model and population monitoring"
        title="Drift is classified before it is escalated."
        summary="Population shift, concept drift, threshold effects, label delay and data quality are monitored as distinct explanations."
        facts={[
          { label: "Model", value: modelName },
          {
            label: "Monitoring status",
            value: monitoringSignal,
            status: monitoringSignal,
          },
          { label: "Reporting scope", value: "Latest drift comparison" },
        ]}
      />
      <ModeNote mode={mode} />
      <section className="model-monitor-grid">
        {data.modelMonitoring.map((item) => (
          <button
            type="button"
            key={item.metric}
            onClick={() =>
              onOpenEvidence({
                eyebrow: "Model monitoring evidence",
                title: item.metric,
                summary: item.note,
                facts: [
                  {
                    label: "Current",
                    value: `${item.current.toFixed(item.current < 1 ? 3 : 2)}${item.unit}`,
                  },
                  {
                    label: "Reference",
                    value: `${item.reference.toFixed(item.reference < 1 ? 3 : 2)}${item.unit}`,
                  },
                  { label: "Status", value: item.status },
                  { label: "Model version", value: modelName },
                ],
                caveat:
                  "Performance metrics use matured outcomes only; label delay is reported separately from model drift.",
              })
            }
          >
            <StatusChip status={item.status} compact />
            <span>{item.metric}</span>
            <strong>{item.current.toFixed(item.current < 1 ? 3 : 2)}{item.unit}</strong>
            <small>Reference {item.reference.toFixed(item.reference < 1 ? 3 : 2)}{item.unit}</small>
            <p>{item.note}</p>
          </button>
        ))}
      </section>
      <div className="content-grid cols-7-5">
        <Panel
          eyebrow="Population drift"
          title="Selected feature stability"
          subtitle="PSI with Jensen–Shannon cross-check · minimum samples met"
        >
          <HorizontalBars
            data={data.modelMonitoring.map((item) => ({
              label: item.metric,
              value: item.current,
              secondary: item.reference,
              status: item.status,
            }))}
            unit=""
            max={Math.max(
              0.25,
              ...data.modelMonitoring.map((item) => item.reference),
            )}
            valueLabel="Watch threshold"
          />
        </Panel>
        <Panel
          eyebrow="Model card"
          title="Approved use and controls"
          subtitle="Versioned governance record"
        >
          <dl className="model-card-list">
            <div><dt>Purpose</dt><dd>Portfolio population-drift monitoring</dd></div>
            <div><dt>Version</dt><dd>{modelName}</dd></div>
            <div><dt>Approved use</dt><dd>Aggregate diagnostics and monitoring</dd></div>
            <div><dt>Prohibited use</dt><dd>Automated customer adverse action</dd></div>
            <div><dt>Measure</dt><dd>PSI with Jensen–Shannon cross-check</dd></div>
            <div><dt>Validation</dt><dd>Population shift is not proof of performance drift</dd></div>
            <div><dt>Monitoring</dt><dd>Latest available baseline/current samples</dd></div>
            <div><dt>Retraining</dt><dd>Explicit versioned command only</dd></div>
          </dl>
        </Panel>
      </div>
      <Panel
        eyebrow="Diagnostic classification"
        title="Returned feature-level drift evidence"
        subtitle="Observed PSI versus the configured watch threshold"
      >
        <div className="drift-classification">
          {data.modelMonitoring.map((item) => (
            <div key={item.metric}>
              <span><strong>{item.metric}</strong><small>{item.note}</small></span>
              <i>
                <em
                  style={{
                    width: `${Math.min(
                      100,
                      (item.current / Math.max(item.reference, 0.0001)) * 100,
                    )}%`,
                  }}
                />
              </i>
              <b>{item.current.toFixed(4)}</b>
              <StatusChip status={item.status} compact />
            </div>
          ))}
        </div>
      </Panel>
    </>
  );
}

export function ExportsPage(props: PageProps) {
  const { data, mode, onOpenEvidence } = props;
  const [queued, setQueued] = useState<string | null>(null);
  const packages = [
    {
      id: "excel",
      type: "XLSX",
      title: "Management information workbook",
      detail: "13 formatted sheets with filters, definitions, assumptions and refresh control",
      filename: "Filename assigned by validated API",
      size: "Generated on request",
      interactive: true,
    },
    {
      id: "powerbi",
      type: "PARQUET + DAX",
      title: "Power BI enablement package",
      detail: "Star-schema tables, relationship map, DAX measures and validation totals",
      filename: "Filename assigned by validated API",
      size: "Generated on request",
      interactive: true,
    },
    {
      id: "csv",
      type: "CSV",
      title: "Granular analytical marts",
      detail: "Paginated metric, vintage, strategy, alert and scenario tables",
      filename: "Documented extension",
      size: "Not generated here",
      interactive: false,
    },
    {
      id: "evidence",
      type: "JSON",
      title: "Audit-ready evidence package",
      detail: "Structured findings, calculation versions, caveats and lineage",
      filename: "Documented extension",
      size: "Not generated here",
      interactive: false,
    },
  ];
  return (
    <>
      <PageHeader
        eyebrow="Export centre"
        title="Take governed definitions into the tools teams already use."
        summary="Every export carries refresh metadata, assumptions, metric versions and reconciliation totals."
        facts={[
          { label: "Latest run", value: data.metadata.runId },
          { label: "Interactive reconciliation", value: "Not asserted" },
          { label: "Reporting month", value: data.metadata.asOf },
        ]}
      />
      <ModeNote mode={mode} />
      <section className="export-package-grid">
        {packages.map((item) => (
          <article key={item.id}>
            <header>
              <span>{item.type}</span>
              <StatusChip status={item.interactive ? "LIVE" : "DOCUMENTED"} compact />
            </header>
            <h2>{item.title}</h2>
            <p>{item.detail}</p>
            <div className="file-row">
              <span>{item.filename}</span>
              <small>{item.size}</small>
            </div>
            {item.interactive ? (
            <button
              type="button"
              className="primary-button is-wide"
              onClick={async () => {
                setQueued(item.id);
                const supported =
                  item.id === "excel" || item.id === "powerbi";
                if (isApiBacked(data) && supported) {
                  try {
                    const artifact = await generateExport(
                      item.id as "excel" | "powerbi",
                    );
                    onOpenEvidence({
                      eyebrow: "Export generated",
                      title: artifact.filename,
                      summary:
                        "The validated backend generated and registered this governed artifact.",
                      facts: [
                        { label: "Artifact ID", value: artifact.artifactId },
                        {
                          label: "Size",
                          value: `${Math.max(1, Math.round(artifact.sizeBytes / 1024)).toLocaleString()} KB`,
                        },
                        { label: "Run ID", value: data.metadata.runId },
                        {
                          label: "Quality status",
                          value: data.metadata.qualityStatus,
                        },
                      ],
                      caveat:
                        "The artifact uses synthetic data and should be reviewed before wider distribution.",
                    });
                    if (artifact.downloadUrl) {
                      window.location.assign(artifact.downloadUrl);
                    }
                    return;
                  } catch (error) {
                    onOpenEvidence({
                      eyebrow: "Export service",
                      title: "Package generation did not complete",
                      summary:
                        error instanceof Error
                          ? error.message
                          : "The export service returned an unknown error.",
                      facts: [
                        { label: "Requested package", value: item.title },
                        { label: "Run ID", value: data.metadata.runId },
                      ],
                      action: "Retry after confirming the validated API is running.",
                    });
                    setQueued(null);
                    return;
                  }
                }
                onOpenEvidence({
                  eyebrow: "Export request",
                  title: item.title,
                  summary: supported
                    ? `${item.filename} is staged in the versioned demonstration view. Connect the validated API to generate the file.`
                    : `${item.filename} is a documented interoperability handoff; this interactive endpoint is not implemented.`,
                  facts: [
                    { label: "Reporting month", value: data.metadata.asOf },
                    { label: "Run ID", value: data.metadata.runId },
                    { label: "Calculation", value: data.metadata.calculationVersion },
                    { label: "Quality status", value: data.metadata.qualityStatus },
                  ],
                  caveat:
                    "Executable backend generation is available for Excel and Power BI. CSV and evidence-bundle endpoints remain documented extensions.",
                });
              }}
            >
              {queued === item.id
                ? "Requested ✓"
                : isApiBacked(data) &&
                    (item.id === "excel" || item.id === "powerbi")
                  ? "Generate & download"
                  : "Review package"}
            </button>
            ) : (
              <span className="read-only-action">Documentation only</span>
            )}
          </article>
        ))}
      </section>
      <div className="content-grid cols-7-5">
        <Panel
          eyebrow="Reconciliation"
          title="API values awaiting package-specific reconciliation"
          subtitle="Generated packages carry their own validation snapshot; this screen does not fabricate cross-tool matches"
        >
          <TableShell label="Export reconciliation totals">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Measure</th>
                  <th>API</th>
                  <th>Excel package</th>
                  <th>Power BI package</th>
                  <th>Interactive status</th>
                </tr>
              </thead>
              <tbody>
                {data.kpis.slice(0, 6).map((item) => {
                  const value = formatMetricValue(item);
                  return (
                    <tr key={item.id}>
                      <th scope="row">{item.shortName}</th>
                      <td>{value}</td>
                      <td>Generate to validate</td>
                      <td>Generate to validate</td>
                      <td><StatusChip status="Watch" compact /> Not asserted</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </TableShell>
        </Panel>
        <Panel
          eyebrow="Package controls"
          title="What travels with an export"
          subtitle="Reproducibility and governance metadata"
        >
          <div className="export-control-list">
            {[
              ["Refresh metadata", data.metadata.refreshedAt],
              ["Run manifest", data.metadata.runId],
              ["Metric registry", data.metadata.calculationVersion],
              ["Scenario assumptions", "Versioned + visible"],
              ["Relationship mapping", "No uncontrolled many-to-many"],
              ["Validation totals", "Package-specific"],
              ["Synthetic flag", "Included on every table"],
            ].map(([label, value]) => (
              <div key={label}><span>{label}</span><strong>{value}</strong></div>
            ))}
          </div>
        </Panel>
      </div>
    </>
  );
}

export function CapabilitiesPage({ data, mode }: PageProps) {
  const nonLive = data.capabilities.filter((item) => item.status !== "LIVE");
  return (
    <>
      <PageHeader
        eyebrow="Capability truth registry"
        title="Capability Status"
        summary="Backend capability records are shown as registered. Endpoint availability never upgrades a feature's governed status."
        facts={[
          { label: "Registry version", value: data.capabilityRegistry.registryVersion },
          { label: "Registered features", value: data.capabilities.length.toString() },
          { label: "Non-live / limited", value: nonLive.length.toString(), status: nonLive.length > 0 ? "Watch" : "Stable" },
        ]}
      />
      <ModeNote mode={mode} />
      <Panel
        eyebrow="Status vocabulary"
        title="What each registry status means"
        subtitle="These exact values come from the governed backend registry"
      >
        <div className="capability-definition-grid">
          {data.capabilityRegistry.allowedStatuses.map((itemStatus) => (
            <article key={itemStatus}>
              <StatusChip status={itemStatus} compact />
              <p>{data.capabilityRegistry.statusDefinitions[itemStatus] ?? "No definition supplied."}</p>
              <strong>{data.capabilityRegistry.statusCounts[itemStatus] ?? 0}</strong>
            </article>
          ))}
        </div>
      </Panel>
      <Panel
        eyebrow="Registry records"
        title="Implemented, limited, disabled and planned capabilities"
        subtitle={`Schema ${data.capabilityRegistry.schemaVersion} · limitations remain visible for every record`}
      >
        <TableShell label="Capability status registry">
          <table className="data-table capability-table">
            <thead>
              <tr>
                <th>Capability</th>
                <th>Status</th>
                <th>Backend endpoint</th>
                <th>Frontend route</th>
                <th>Evidence</th>
                <th>Limitation</th>
                <th>Validated</th>
              </tr>
            </thead>
            <tbody>
              {data.capabilities.map((item) => (
                <tr key={item.featureId} className={item.status === "LIVE" ? "" : "is-limited"}>
                  <th scope="row">
                    {item.name}
                    <small>{item.featureId} · v{item.version}</small>
                  </th>
                  <td><StatusChip status={item.status} compact /></td>
                  <td>{item.backendEndpoints.length > 0 ? item.backendEndpoints.join(", ") : "N/A"}</td>
                  <td>{item.frontendRoutes.length > 0 ? item.frontendRoutes.join(", ") : "N/A"}</td>
                  <td>
                    {item.testEvidence.length > 0
                      ? `${item.testEvidence.length} test reference${item.testEvidence.length === 1 ? "" : "s"}`
                      : "No executable test supplied"}
                  </td>
                  <td><span className="capability-limitation">{item.limitation}</span></td>
                  <td>{item.lastValidationDate}<small>{item.owner}</small></td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableShell>
      </Panel>
    </>
  );
}

export function PageContent({
  view,
  props,
}: {
  view: ViewKey;
  props: PageProps;
}) {
  switch (view) {
    case "start-here":
    case "samples":
    case "how-naim":
    case "why-naim":
    case "data-onboarding":
      return (
        <DataState
          type="empty"
          title="Experience route is rendered by the workbench shell"
          detail="Return to the requested route through the primary navigation."
        />
      );
    case "executive":
      return <ExecutivePage {...props} />;
    case "trends":
      return <TrendsPage {...props} />;
    case "root-cause":
      return <RootCausePage {...props} />;
    case "vintage":
      return <VintagePage {...props} />;
    case "strategy":
      return <StrategyPage {...props} />;
    case "partners":
      return <PartnersPage {...props} />;
    case "vendors":
      return <VendorsPage {...props} />;
    case "membership":
      return <MembershipPage {...props} />;
    case "baskets":
      return <BasketsPage {...props} />;
    case "finance":
      return <FinancePage {...props} />;
    case "market-risk":
      return <MarketRiskPage {...props} />;
    case "advanced-statistics":
      return <AdvancedStatisticsPage {...props} />;
    case "data-quality":
      return <DataQualityPage {...props} />;
    case "forecast":
      return <ForecastPage {...props} />;
    case "alerts":
      return <AlertsPage {...props} />;
    case "investigations":
      return <InvestigationsPage {...props} />;
    case "model-monitoring":
      return <ModelMonitoringPage {...props} />;
    case "exports":
      return <ExportsPage {...props} />;
    case "methodology":
      return <MethodologyPage {...props} />;
    case "capabilities":
      return <CapabilitiesPage {...props} />;
    case "instant-demo":
      return (
        <DataState
          type="empty"
          title="Instant Demo opens from its dedicated landing page"
          detail="Return to the Instant Demo route while DEMO mode is active."
        />
      );
  }
}
