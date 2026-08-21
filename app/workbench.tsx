"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import {
  applyPortfolioStoryEvidence,
  createEmptyWorkbenchData,
  EMPTY_CLIENT_REQUEST_DIAGNOSTICS,
  filtersForPortfolioStory,
  GovernedWorkflowError,
  getInitialWorkbenchData,
  loadWorkbenchData,
  runPortfolioStory,
} from "./data/api-client";
import {
  INITIAL_PORTFOLIO_STORY_STATE,
  earlyWarningHeadline,
  portfolioStoryAvailable,
  portfolioStoryReducer,
  PORTFOLIO_STORY_SECONDS,
} from "./data/p0-contract";
import {
  diagnosticDisplayStatus,
  hasCriticalRequestFailure,
  retryStateReducer,
} from "./data/governed-evidence";
import { activeAlertQueue } from "./data/alert-lifecycle";
import { DEFAULT_FILTERS, EMPTY_FILTERS } from "./data/demo-data";
import { PageContent } from "./components/pages";
import {
  HowNaimPage,
  SamplesPage,
  StartHerePage,
  WhyNaimPage,
} from "./components/start-pages";
import type { PreparedSampleId } from "./components/start-pages";
import { DataOnboardingPage } from "./components/onboarding-page";
import {
  DataState,
  EvidenceDrawer,
  SegmentedControl,
  StatusChip,
} from "./components/ui";
import type {
  AlertRecord,
  EvidenceItem,
  ClientRequestDiagnostics,
  GlobalFilters,
  PortfolioStoryRun,
  RetryState,
  ViewKey,
  WorkbenchData,
  WorkbenchMode,
} from "./workbench-types";

const viewLabels: Record<ViewKey, string> = {
  "start-here": "Start Here",
  samples: "Try a Sample",
  "how-naim": "How nAIM Works",
  "why-naim": "Why nAIM",
  "data-onboarding": "Use Your Own Local Data",
  executive: "Executive Command Centre",
  trends: "Portfolio Trends",
  "root-cause": "Root-Cause Explorer",
  vintage: "Vintage Explorer",
  strategy: "Strategy Impact Lab",
  partners: "Partner Control Tower",
  vendors: "Vendor Oversight",
  membership: "Membership Value–Risk",
  baskets: "Baskets & Workspaces",
  finance: "Finance Analytics",
  "market-risk": "Market Risk & Volatility Lab",
  "advanced-statistics": "Advanced Statistics Status",
  "data-quality": "Data Quality & Lineage",
  forecast: "Forecast & Stress",
  alerts: "Early-Warning Alerts",
  investigations: "Investigation Queue",
  "model-monitoring": "Model Monitoring",
  methodology: "Methodology",
  exports: "Export Centre",
  capabilities: "Capability Status",
  "instant-demo": "Instant Demo",
};

const navGroups: Array<{
  label: string;
  items: Array<{ view: ViewKey; short: string; label: string; badge?: string }>;
}> = [
  {
    label: "START",
    items: [
      { view: "start-here", short: "01", label: "Start Here" },
      { view: "samples", short: "02", label: "Try a Sample" },
      { view: "instant-demo", short: "03", label: "Demo & Tour" },
      { view: "how-naim", short: "04", label: "How nAIM Works" },
      { view: "why-naim", short: "05", label: "Why nAIM" },
      { view: "data-onboarding", short: "⇧", label: "Use Local Data" },
    ],
  },
  {
    label: "MONITOR",
    items: [
      { view: "executive", short: "CC", label: "Command Centre" },
      { view: "trends", short: "TR", label: "Portfolio Trends" },
      { view: "vintage", short: "VG", label: "Vintage Explorer" },
      { view: "alerts", short: "EW", label: "Early Warning" },
    ],
  },
  {
    label: "DIAGNOSE",
    items: [
      { view: "root-cause", short: "RC", label: "Root Cause" },
      { view: "strategy", short: "ST", label: "Strategy Impact" },
      { view: "finance", short: "FN", label: "Finance Analytics" },
      { view: "market-risk", short: "MR", label: "Market Risk Lab" },
      { view: "advanced-statistics", short: "AS", label: "Advanced Statistics" },
    ],
  },
  {
    label: "DECIDE",
    items: [
      { view: "forecast", short: "SC", label: "Scenario" },
      { view: "investigations", short: "IQ", label: "Investigations" },
      { view: "baskets", short: "BK", label: "Baskets & Workspaces" },
      { view: "partners", short: "PT", label: "Partners" },
      { view: "vendors", short: "VN", label: "Vendors" },
      { view: "membership", short: "MB", label: "Membership" },
    ],
  },
  {
    label: "GOVERN",
    items: [
      { view: "data-quality", short: "DQ", label: "Data Quality" },
      { view: "model-monitoring", short: "MM", label: "Model Monitoring" },
      { view: "methodology", short: "MD", label: "Methodology" },
      { view: "capabilities", short: "CS", label: "Capability Status" },
    ],
  },
  {
    label: "DELIVER",
    items: [
      { view: "exports", short: "EX", label: "Export Centre" },
    ],
  },
];

const validViews = new Set<ViewKey>(Object.keys(viewLabels) as ViewKey[]);
const alwaysAvailableExperienceViews = new Set<ViewKey>([
  "start-here",
  "samples",
  "how-naim",
  "why-naim",
  "data-onboarding",
]);
const chromeLightExperienceViews = new Set<ViewKey>([
  ...alwaysAvailableExperienceViews,
  "instant-demo",
]);
type RouteKey = ViewKey | "not-found";

function resolveView(initialRoute: string): RouteKey {
  if (validViews.has(initialRoute as ViewKey)) return initialRoute as ViewKey;
  return "not-found";
}

function pathFor(view: ViewKey): string {
  return view === "start-here" ? "/" : `/${view}`;
}

interface DemoStep {
  label: string;
  view: ViewKey;
  eyebrow: string;
  title: string;
  detail: string;
  evidence: (data: WorkbenchData, story: PortfolioStoryRun | null) => EvidenceItem;
}

function metricNumber(
  data: WorkbenchData,
  metricId: string,
  field: "value" | "prior",
): number | null {
  const value = data.kpis.find((item) => item.id === metricId)?.[field];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function contributionPercent(value: number): number {
  return value * 100;
}

function strongestVintage(data: WorkbenchData) {
  return [...data.vintages]
    .filter((item) => item.mob >= 4 && item.mob <= 8 && !item.maturityWarning)
    .sort(
      (left, right) =>
        right.delinquency30 - left.delinquency30 ||
        right.cohortSize - left.cohortSize,
    )[0];
}

const DEMO_STEPS: DemoStep[] = [
  {
    label: "Problem",
    view: "why-naim",
    eyebrow: "00–06 seconds · problem",
    title: "One portfolio. Many tools. One analytical chain at risk.",
    detail:
      "Data moves through SQL, Python or SAS, Excel, BI and PowerPoint—creating repeated opportunities for scope and definition drift.",
    evidence: (data) => ({
      eyebrow: "Demo evidence · problem framing",
      title: "The analytical hand-off risk",
      summary:
        "nAIM complements the finance toolchain by preserving a governed identity across calculations, review surfaces and outputs.",
      facts: [
        { label: "Active source mode", value: data.metadata.dataMode },
        { label: "Calculation version", value: data.metadata.calculationVersion },
        { label: "Toolchain", value: "Data → SQL → Python / SAS → Excel → BI → PowerPoint" },
        { label: "Control objective", value: "One definition, scope and evidence chain" },
      ],
      caveat:
        "nAIM does not replace production systems or enterprise presentation tools.",
    }),
  },
  {
    label: "Trust",
    view: "data-quality",
    eyebrow: "06–11 seconds · trust",
    title: "Scope and provenance are bound before interpretation.",
    detail:
      "Reporting period, comparison period, data quality, data mode, dataset and configuration are made visible together.",
    evidence: (data) => ({
      eyebrow: "Demo evidence · scope and trust",
      title: `${data.metadata.asOf} versus ${data.metadata.comparisonPeriod}`,
      summary:
        "The active analytical state declares its source mode and binds the governed run before any result is promoted.",
      facts: [
        { label: "Reporting period", value: data.metadata.asOf },
        { label: "Comparison period", value: data.metadata.comparisonPeriod },
        { label: "Data mode", value: data.metadata.dataMode },
        { label: "Data quality", value: data.metadata.qualityStatus },
        { label: "Dataset hash", value: data.metadata.sourceContext.datasetHash ?? "Not returned" },
        { label: "Configuration hash", value: data.metadata.sourceContext.configurationHash ?? "Not returned" },
      ],
      caveat:
        "A declared mode is not a quality conclusion; publication gates and provenance checks remain separate controls.",
    }),
  },
  {
    label: "Movement",
    view: "executive",
    eyebrow: "11–18 seconds · movement",
    title: "Loss rate moved materially.",
    detail:
      "The command centre separates the adverse signal from healthy growth and lower fraud.",
    evidence: (data) => {
      const loss = data.kpis.find(
        (item) => item.id === "ANNUALISED_LOSS_RATE",
      );
      const current = metricNumber(data, "ANNUALISED_LOSS_RATE", "value");
      const prior = metricNumber(data, "ANNUALISED_LOSS_RATE", "prior");
      return {
        eyebrow: "Demo evidence · detected movement",
        title: "Annualised loss rate increased",
        summary:
          "The governed metric moved beyond both practical and statistical review criteria.",
        facts: [
          {
            label: "Current",
            value: current === null ? "Not available" : `${current.toFixed(2)}%`,
          },
          {
            label: "Prior",
            value: prior === null ? "Not available" : `${prior.toFixed(2)}%`,
          },
          {
            label: "Observed movement",
            value: `+${data.rootCause.finding.observedChangeBps.toFixed(1)} bps`,
          },
          {
            label: "Denominator",
            value: loss?.denominator ?? "See governed metric registry",
          },
          {
            label: "Statistical evidence",
            value: loss?.statisticalStatus ?? "Review criteria applied",
          },
        ],
        caveat:
          "This is a validated movement, not yet an explanation or policy recommendation.",
      };
    },
  },
  {
    label: "Cause",
    view: "root-cause",
    eyebrow: "18–27 seconds · cause",
    title: "Mix and performance both contributed.",
    detail:
      "Exact decomposition reconciles the full movement and identifies Affiliate as the largest lens.",
    evidence: (data) => {
      const finding = data.rootCause.finding;
      const share = contributionPercent(finding.contributionShare);
      const residual =
        finding.observedChangeBps -
        finding.mixContributionBps -
        finding.withinSegmentContributionBps;
      return {
        eyebrow: "Demo evidence · exact decomposition",
        title: `${finding.primaryDriver} is the largest single driver`,
        summary:
          "A symmetric rate decomposition separates population mix from within-segment performance.",
        facts: [
          {
            label: "Mix contribution",
            value: `${finding.mixContributionBps >= 0 ? "+" : ""}${finding.mixContributionBps.toFixed(1)} bps`,
          },
          {
            label: "Within-segment",
            value: `${finding.withinSegmentContributionBps >= 0 ? "+" : ""}${finding.withinSegmentContributionBps.toFixed(1)} bps`,
          },
          { label: "Residual", value: `${residual.toFixed(1)} bps` },
          {
            label: "Primary lens",
            value: `${finding.primaryDriver} · ${share.toFixed(1)}%`,
          },
        ],
        caveat:
          "Dimensions are separately reconciled and cannot be added across overlapping populations; a driver can exceed 100% when offset by favourable segments.",
        action: `Inspect maturity-aligned ${finding.primaryDriver} cohorts.`,
      };
    },
  },
  {
    label: "Vintage",
    view: "vintage",
    eyebrow: "27–34 seconds · vintage",
    title: "Recent Affiliate cohorts weakened at MOB 4–8.",
    detail:
      "Maturity alignment and confidence intervals prevent young vintages from being compared unfairly.",
    evidence: (data) => {
      const cell = strongestVintage(data);
      return {
        eyebrow: "Demo evidence · vintage",
        title: cell
          ? `${cell.vintage} · month ${cell.mob}`
          : "Maturity-aligned recent cohort",
        summary:
          "The recent cohort is above mature comparators at a common months-on-book point.",
        facts: [
          {
            label: "30+ delinquency",
            value:
              cell === undefined
                ? "Not available"
                : `${cell.delinquency30.toFixed(2)}%`,
          },
          {
            label: "95% interval",
            value:
              cell === undefined
                ? "Not available"
                : `${cell.confidenceLow.toFixed(2)}%–${cell.confidenceHigh.toFixed(2)}%`,
          },
          {
            label: "Original cohort",
            value: cell?.cohortSize.toLocaleString() ?? "Not available",
          },
          { label: "Comparison rule", value: "Common maturity only" },
        ],
        caveat:
          "Incomplete young vintages remain explicitly flagged and are not ranked against fully mature lifetime outcomes.",
      };
    },
  },
  {
    label: "Strategy",
    view: "strategy",
    eyebrow: "34–42 seconds · strategy",
    title: "Challenger B reduced fraud but increased friction.",
    detail:
      "The test clears assignment checks, yet fails practical profit and operations guardrails.",
    evidence: (data) => {
      const champion = data.strategies.find(
        (item) => item.strategy === "Champion A",
      );
      const challenger = data.strategies.find(
        (item) => item.strategy === "Challenger B",
      );
      return {
        eyebrow: "Demo evidence · strategy",
        title: "Broader outcomes overturn the fraud-only view",
        summary:
          "The configured deterministic framework returns Investigate—not Expand.",
        facts: [
          {
            label: "Fraud difference",
            value: `${((challenger?.fraudBps ?? 7.5) - (champion?.fraudBps ?? 9.2)).toFixed(1)} bps`,
          },
          {
            label: "Review difference",
            value: `+${((challenger?.reviewRate ?? 7.3) - (champion?.reviewRate ?? 4.5)).toFixed(1)} pp`,
          },
          {
            label: "Friction difference",
            value: `+${((challenger?.frictionRate ?? 10.2) - (champion?.frictionRate ?? 6.4)).toFixed(1)} pp`,
          },
          { label: "Operations capacity", value: "Not returned by API" },
          {
            label: "Rule outcome",
            value: data.strategyRecommendation?.decision ?? "Not available",
          },
        ],
        caveat:
          "The conclusion applies to the valid experimental population and is not an automatic customer-level strategy decision.",
      };
    },
  },
  {
    label: "Warning",
    view: "alerts",
    eyebrow: "42–48 seconds · warning",
    title: "The alert hierarchy separates signal from noise.",
    detail:
      "Threshold, denominator, recurrence, ownership and statistical state travel with each durable signal.",
    evidence: (data) => {
      const activeAlerts = activeAlertQueue(data.alerts);
      const alert = activeAlerts[0] ?? data.alerts[0];
      return {
        eyebrow: "Demo evidence · early warning",
        title: earlyWarningHeadline(activeAlerts),
        summary:
          alert?.title ?? "No workflow-active alert was returned for the governed scope.",
        facts: [
          { label: "Metric", value: alert?.metric ?? "Not available" },
          { label: "Threshold", value: alert?.threshold ?? "Not available" },
          { label: "Current value", value: alert?.current ?? "Not available" },
          { label: "Owner", value: alert?.owner ?? "Not available" },
          { label: "Recurrence", value: alert?.lifecycle?.recurrenceCount.toString() ?? "Not returned" },
          { label: "Status", value: alert?.state ?? "Not available" },
          { label: "Sample adequacy", value: alert?.lifecycle ? `${alert.lifecycle.latestEvidence.denominator.toLocaleString()} observations` : "See evidence" },
          { label: "Statistical state", value: alert?.evidence.find((item) => item.toLowerCase().includes("stat")) ?? "No inference promoted" },
        ],
        caveat:
          "An alert is a governed review signal, not an automatic policy action.",
        action: "Acknowledge or open an investigation using the server-authorized workflow.",
      };
    },
  },
  {
    label: "Scenario",
    view: "forecast",
    eyebrow: "48–54 seconds · scenario",
    title: "Mild stress makes the downside visible.",
    detail:
      "Editable assumptions transmit transparently into delinquency, loss, workload and expected profit.",
    evidence: (data) => {
      const mild = data.scenarios.find(
        (item) =>
          item.id === "mild" ||
          item.id === "mild-downturn" ||
          item.name === "Mild Downturn",
      );
      return {
        eyebrow: "Demo evidence · scenario",
        title: "Mild Downturn planning estimate",
        summary:
          "Moderate synthetic stress reduces twelve-month expected profit and increases cumulative loss.",
        facts: [
          {
            label: "Consumer stress index",
            value: mild?.assumptions.consumerStress.toFixed(0) ?? "Not available",
          },
          {
            label: "Unemployment assumption",
            value:
              mild === undefined
                ? "Not available"
                : `${mild.assumptions.unemployment.toFixed(1)}%`,
          },
          {
            label: "Cumulative loss",
            value: `$${(mild?.cumulativeLoss ?? 5.74).toFixed(2)}m`,
          },
          {
            label: "Expected profit delta",
            value: `$${(mild?.deltaFromBaseline ?? -7.3).toFixed(1)}m`,
          },
        ],
        caveat:
          "This is a portfolio-planning scenario with synthetic elasticities, not a regulatory capital scenario.",
      };
    },
  },
  {
    label: "Action",
    view: "investigations",
    eyebrow: "54–60 seconds · action",
    title: "A governed investigation is staged.",
    detail:
      "The signal is assigned with hypothesis, evidence, SLA and an auditable next action.",
    evidence: (data, story) => {
      const investigation = story?.investigation ?? {};
      const commentary = story?.commentary ?? {};
      const investigationId = String(
        investigation.investigation_id ?? investigation.id ?? data.investigations[0]?.id ?? "Not returned",
      );
      return {
      eyebrow: "Demo evidence · workflow mutation",
      title: `${investigationId} created or reused`,
      summary:
        "The governed demo service creates or reuses the matching investigation and returns deterministic evidence-backed commentary.",
      facts: [
        { label: "Investigation", value: investigationId },
        { label: "Recommended next step", value: story?.story.supportedAction ?? data.interpretation.priority },
        { label: "Confidence", value: String(commentary.confidence ?? "Evidence-bound; review required") },
        { label: "Approval requirement", value: "Human approval required" },
        { label: "Commentary provider", value: String(commentary.provider ?? data.commentary.provider) },
      ],
      action:
        "Validate acquisition-score distribution and review Challenger B eligibility.",
      caveat:
        "The workflow does not imply an automatic customer or policy decision.",
      };
    },
  },
  {
    label: "Outputs",
    view: "exports",
    eyebrow: "60–67 seconds · outputs",
    title: "The evidence is ready for enterprise tools.",
    detail:
      "Excel, Power BI, CSV and JSON packages reconcile to the same governed metric versions.",
    evidence: (data) => ({
      eyebrow: "Demo evidence · export",
      title: "Audit-ready package queued",
      summary:
        "The current filtered scope, run manifest, metric registry and scenario assumptions are ready for export.",
      facts: [
        { label: "Run ID", value: data.metadata.runId },
        { label: "Excel workbook", value: "13 sheets" },
        { label: "Power BI", value: "Star schema + DAX" },
        { label: "API reconciliation", value: "Run in exported package" },
        { label: "Synthetic flag", value: "Included" },
      ],
      caveat:
        "nAIM complements enterprise presentation tools by preserving the governed analytical logic and evidence.",
    }),
  },
];

function FilterSelect({
  label,
  value,
  options,
  onChange,
  compact = false,
  disabled = false,
  title,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  compact?: boolean;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <label
      className={`filter-select ${compact ? "is-compact" : ""}`}
      title={title}
    >
      <span>{label}</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
    </label>
  );
}

function GlobalFilterBar({
  filters,
  data,
  activeView,
  onChange,
  onReset,
}: {
  filters: GlobalFilters;
  data: WorkbenchData;
  activeView: ViewKey;
  onChange: (filters: GlobalFilters) => void;
  onReset: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const liveApi =
    data.metadata.dataMode === "LIVE" ||
    data.metadata.dataMode === "OFFLINE_SNAPSHOT";
  const dimensionFiltersSupported = new Set<ViewKey>([
    "executive",
    "trends",
    "root-cause",
    "vintage",
    "strategy",
    "alerts",
  ]).has(activeView);
  const reportingMonthSupported = !new Set<ViewKey>([
    "baskets",
    "market-risk",
    "advanced-statistics",
    "data-quality",
    "investigations",
    "model-monitoring",
    "methodology",
    "exports",
  ]).has(activeView);
  const dimensionDisabled = liveApi && !dimensionFiltersSupported;
  const dimensionTitle = dimensionDisabled
    ? "This module returns its own current/global scope; dimensional portfolio filters do not apply."
    : undefined;
  const selectedCount = Object.entries(filters).filter(
    ([key, value]) =>
      key !== "reportingMonth" &&
      key !== "comparison" &&
      !value.startsWith("All "),
  ).length;
  const update = <K extends keyof GlobalFilters>(
    key: K,
    value: GlobalFilters[K],
  ) => onChange({ ...filters, [key]: value });
  return (
    <section className="global-filter-bar" aria-label="Global portfolio filters">
      <div className="filter-primary">
        <FilterSelect
          label="Reporting month"
          value={filters.reportingMonth}
          options={data.filterOptions.reportingMonths}
          onChange={(value) => update("reportingMonth", value)}
          disabled={liveApi && !reportingMonthSupported}
          title={
            liveApi && !reportingMonthSupported
              ? "This module returns current/global scope rather than historical reconstruction."
              : undefined
          }
        />
        <FilterSelect
          label="Compare with"
          value={filters.comparison}
          options={data.filterOptions.comparisons}
          onChange={(value) => update("comparison", value)}
          disabled={liveApi}
          title={
            liveApi
              ? "The validated API currently supports prior-month comparison."
              : undefined
          }
        />
        <FilterSelect
          label="Product"
          value={filters.product}
          options={data.filterOptions.products}
          onChange={(value) => update("product", value)}
          disabled={dimensionDisabled}
          title={dimensionTitle}
        />
        <FilterSelect
          label="Acquisition channel"
          value={filters.channel}
          options={data.filterOptions.channels}
          onChange={(value) => update("channel", value)}
          disabled={dimensionDisabled}
          title={dimensionTitle}
        />
        <FilterSelect
          label="Geography"
          value={filters.geography}
          options={data.filterOptions.geographies}
          onChange={(value) => update("geography", value)}
          disabled={dimensionDisabled}
          title={dimensionTitle}
        />
        <button
          type="button"
          className={`advanced-filter-button ${selectedCount > 0 ? "has-selection" : ""}`}
          onClick={() => setExpanded((current) => !current)}
          aria-expanded={expanded}
        >
          <span aria-hidden="true">≡</span>
          More filters
          {selectedCount > 0 ? <b>{selectedCount}</b> : null}
        </button>
        <button type="button" className="reset-filter-button" onClick={onReset}>
          <span aria-hidden="true">↺</span>
          Reset
        </button>
      </div>
      {dimensionDisabled || (liveApi && !reportingMonthSupported) ? (
        <div className="filter-scope-note" role="note">
          <strong>Module scope:</strong>{" "}
          {liveApi && !reportingMonthSupported
            ? "current/global API state; reporting month and portfolio dimensions do not apply."
            : "reporting month applies, while portfolio dimensions do not apply to this module endpoint."}
        </div>
      ) : null}
      {expanded ? (
        <div className="filter-advanced">
          <FilterSelect
            label="Customer segment"
            value={filters.segment}
            options={data.filterOptions.segments}
            onChange={(value) => update("segment", value)}
            compact
            disabled={dimensionDisabled}
            title={dimensionTitle}
          />
          <FilterSelect
            label="Risk band"
            value={filters.riskBand}
            options={data.filterOptions.riskBands}
            onChange={(value) => update("riskBand", value)}
            compact
            disabled={dimensionDisabled}
            title={dimensionTitle}
          />
          <FilterSelect
            label="Strategy"
            value={filters.strategy}
            options={data.filterOptions.strategies}
            onChange={(value) => update("strategy", value)}
            compact
            disabled={dimensionDisabled}
            title={dimensionTitle}
          />
          <FilterSelect
            label="Vintage"
            value={filters.vintage}
            options={data.filterOptions.vintages}
            onChange={(value) => update("vintage", value)}
            compact
            disabled={liveApi}
            title={
              liveApi
                ? "Vintage is controlled inside the maturity-aligned explorer."
                : undefined
            }
          />
          <FilterSelect
            label="Model version"
            value={filters.modelVersion}
            options={data.filterOptions.modelVersions}
            onChange={(value) => update("modelVersion", value)}
            compact
            disabled={dimensionDisabled}
            title={dimensionTitle}
          />
          <div className="filter-grain">
            <span>Analytical grain</span>
            <strong>Account-month</strong>
            <small>Double-counting control active</small>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function InstantDemoLanding({
  onStart,
  data,
  starting,
  error,
  presenterMode,
  reduceMotion,
  onTogglePresenter,
  onToggleMotion,
}: {
  onStart: () => void;
  data: WorkbenchData;
  starting: boolean;
  error: string | null;
  presenterMode: boolean;
  reduceMotion: boolean;
  onTogglePresenter: () => void;
  onToggleMotion: () => void;
}) {
  const share = contributionPercent(data.rootCause.finding.contributionShare);
  const residual =
    data.rootCause.finding.observedChangeBps -
    data.rootCause.finding.mixContributionBps -
    data.rootCause.finding.withinSegmentContributionBps;
  return (
    <div className="instant-demo-landing">
      <div className="demo-landing-copy">
        <div className="eyebrow">Interactive 60–70 second demo</div>
        <h1>One movement. Ten governed stages. One evidence chain.</h1>
        <p>
          Watch nAIM frame the industry problem, bind scope and trust, detect a
          material movement, reconcile its causes, align vintages, test strategy
          trade-offs, surface an early warning, stress the outlook, create an
          investigation and carry the evidence into outputs.
        </p>
        <p className="demo-brand-line">
          <strong>Name the movement. Own the evidence.</strong> nAIM is pronounced
          “name”; AIM means All Is Mine.
        </p>
        <div className="demo-proof-row">
          <span>
            <strong>{data.rootCause.finding.observedChangeBps.toFixed(1)} bps</strong>
            <small>observed loss movement</small>
          </span>
          <span>
            <strong>{share.toFixed(1)}%</strong>
            <small>{data.rootCause.finding.primaryDriver} contribution share</small>
          </span>
          <span>
            <strong>{residual.toFixed(1)} bps</strong>
            <small>decomposition residual</small>
          </span>
        </div>
        <button
          type="button"
          className="demo-start-button"
          onClick={onStart}
          disabled={starting}
        >
          <span aria-hidden="true">▶</span>
          {starting ? "Starting governed portfolio story…" : "Run 60-Second Portfolio Story"}
        </button>
        <div className="demo-landing-settings" role="group" aria-label="Demo presentation settings">
          <button type="button" onClick={onTogglePresenter} aria-pressed={presenterMode}>
            {presenterMode ? "Exit Presenter Mode" : "Enter Presenter Mode"}
          </button>
          <label>
            <input type="checkbox" checked={reduceMotion} onChange={onToggleMotion} />
            <span>Reduce Motion</span>
          </label>
        </div>
        <div className="demo-mode-confirmation" role="status">
          <span>Active data mode</span>
          <strong>{data.metadata.dataMode}</strong>
          <small>{data.metadata.qualityStatus} · {data.metadata.asOf} vs {data.metadata.comparisonPeriod}</small>
        </div>
        {error ? (
          <div className="demo-launch-error" role="alert">
            <strong>Portfolio story did not start</strong>
            <span>{error}</span>
          </div>
        ) : null}
        <small className="demo-disclaimer">
          Synthetic data · institution-neutral · no customer-level decisions
        </small>
      </div>
      <div className="demo-sequence-card">
        <header>
          <span>Live sequence</span>
          <strong>01:07</strong>
        </header>
        <ol>
          {DEMO_STEPS.map((step, index) => (
            <li key={step.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div>
                <strong>{step.label}</strong>
                <small>{step.title}</small>
              </div>
            </li>
          ))}
        </ol>
        <footer>
          <span>Stages a session investigation</span>
          <span>Opens calculation evidence</span>
        </footer>
      </div>
    </div>
  );
}

function DemoDock({
  step,
  elapsed,
  running,
  paused,
  complete,
  story,
  activeMode,
  presenterMode,
  reduceMotion,
  onPause,
  onNext,
  onPrevious,
  onClose,
  onRestart,
  onOpenEvidence,
  onAnalyst,
  onTogglePresenter,
  onToggleMotion,
  onSelectStep,
}: {
  step: number;
  elapsed: number;
  running: boolean;
  paused: boolean;
  complete: boolean;
  story: PortfolioStoryRun["story"];
  activeMode: string;
  presenterMode: boolean;
  reduceMotion: boolean;
  onPause: () => void;
  onNext: () => void;
  onPrevious: () => void;
  onClose: () => void;
  onRestart: () => void;
  onOpenEvidence: () => void;
  onAnalyst: () => void;
  onTogglePresenter: () => void;
  onToggleMotion: () => void;
  onSelectStep: (step: number) => void;
}) {
  const current = DEMO_STEPS[Math.min(step, DEMO_STEPS.length - 1)];
  const remaining = Math.max(0, Math.ceil(PORTFOLIO_STORY_SECONDS - elapsed));
  const remainingLabel = `${String(Math.floor(remaining / 60)).padStart(2, "0")}:${String(remaining % 60).padStart(2, "0")}`;
  return (
    <aside className={`demo-dock ${complete ? "is-complete" : ""}`} aria-live="polite">
      <div
        className="demo-progress"
        style={{ "--progress": `${Math.min(100, (elapsed / PORTFOLIO_STORY_SECONDS) * 100)}%` } as React.CSSProperties}
      >
        <i />
      </div>
      <header>
        <span className="demo-live-mark"><i /> {complete ? "Complete" : paused ? "Paused" : "Portfolio story"}</span>
        <strong>{complete ? "01:07" : remainingLabel}</strong>
        <button type="button" onClick={onClose} aria-label="Close instant demo">×</button>
      </header>
      <div className="demo-active-mode"><span>Active data mode</span><strong>{activeMode}</strong></div>
      {complete ? (
        <div className="demo-result-summary">
          <strong>Governed portfolio story complete</strong>
          <dl>
            <div><dt>What changed?</dt><dd>{story.whatChanged}</dd></div>
            <div><dt>Why?</dt><dd>{story.why}</dd></div>
            <div><dt>What remains uncertain?</dt><dd>{story.uncertainties.join(" · ") || "No uncertainty statement returned."}</dd></div>
            <div><dt>What action is supported?</dt><dd>{story.supportedAction}</dd></div>
            <div><dt>What evidence was produced?</dt><dd>{story.evidenceProduced.join(" · ") || "No evidence list returned."}</dd></div>
            <div><dt>What outputs are available?</dt><dd>{story.outputsAvailable.join(" · ") || "No validated output returned."}</dd></div>
          </dl>
          <div className="demo-output-chain" aria-label="Governed output chain">
            <strong>One governed analysis run</strong>
            <span>Dashboard</span><span>Excel</span><span>PowerPoint</span><span>BI</span><span>Evidence</span>
            <small>Same metric definition · same reporting scope · same evidence IDs</small>
          </div>
        </div>
      ) : (
        <div className="demo-current">
          <span>{String(step + 1).padStart(2, "0")}</span>
          <div>
            <small>{current.eyebrow}</small>
            <strong>{current.title}</strong>
            <p>{current.detail}</p>
          </div>
        </div>
      )}
      <footer>
        <div className="demo-pips" aria-label={`Stage ${step + 1} of ${DEMO_STEPS.length}`}>
          {DEMO_STEPS.map((item, index) => (
            <button
              type="button"
              key={item.title}
              className={index < step ? "is-done" : index === step ? "is-current" : ""}
              aria-current={index === step ? "step" : undefined}
              aria-label={`Go to ${item.label} stage`}
              onClick={() => onSelectStep(index)}
            >
              <i aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          ))}
        </div>
        {complete ? (
          <div className="demo-controls is-complete">
            <button type="button" onClick={onRestart}>↺ Restart</button>
            <button type="button" onClick={onOpenEvidence}>Open Evidence</button>
            <button type="button" onClick={onTogglePresenter}>{presenterMode ? "Exit Presenter Mode" : "Presenter Mode"}</button>
            <button type="button" onClick={onAnalyst}>Switch to Analyst View</button>
            <button type="button" onClick={onClose}>Exit Demo</button>
          </div>
        ) : (
          <div className="demo-controls">
            <button type="button" onClick={onPause}>
              {running && !paused ? "Ⅱ Pause" : "▶ Resume"}
            </button>
            <button type="button" onClick={onPrevious} disabled={step === 0}>← Previous</button>
            <button type="button" onClick={onNext}>Next →</button>
            <button type="button" onClick={onRestart}>↺ Restart</button>
            <button type="button" onClick={onOpenEvidence}>Open Evidence</button>
            <button type="button" onClick={onTogglePresenter}>{presenterMode ? "Exit Presenter Mode" : "Presenter Mode"}</button>
            <label className="demo-motion-control">
              <input type="checkbox" checked={reduceMotion} onChange={onToggleMotion} />
              <span>Reduce Motion</span>
            </label>
            <button type="button" onClick={onAnalyst}>Switch to Analyst View</button>
            <button type="button" onClick={onClose}>Exit Demo</button>
          </div>
        )}
      </footer>
    </aside>
  );
}

function diagnosticFact(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "Not reported";
  return typeof value === "number" ? value.toLocaleString("en-US") : value;
}

function DiagnosticPanel({
  data,
  client,
  retryState,
  onRetry,
}: {
  data: WorkbenchData;
  client: ClientRequestDiagnostics;
  retryState: RetryState;
  onRetry: () => void;
}) {
  const server = data.metadata.serverDiagnostics;
  const displayStatus = diagnosticDisplayStatus(
    data.metadata.dataMode,
    server,
    client,
    retryState,
  );
  const retryLabel =
    retryState === "RETRYING"
      ? "Retrying"
      : retryState === "CONNECTED"
        ? "Connected"
        : retryState === "STILL_UNAVAILABLE"
          ? "Still unavailable"
          : "Not retried";
  const responseTime = client.responseTimeMs === null
    ? "Not reported"
    : `${client.responseTimeMs.toFixed(1)} ms`;
  const age = server.snapshot.ageSeconds === null
    ? "Not reported"
    : `${server.snapshot.ageSeconds.toLocaleString("en-US")} seconds`;
  const staleAfter = server.snapshot.staleAfterSeconds === null
    ? "Not reported"
    : `${server.snapshot.staleAfterSeconds.toLocaleString("en-US")} seconds`;
  return (
    <section
      className={`diagnostic-panel diagnostic-${displayStatus.toLowerCase()}`}
      aria-label="Data diagnostics"
      aria-live="polite"
    >
      <header>
        <div>
          <div className="eyebrow">Connection and evidence diagnostics</div>
          <h2>Governed data diagnostics</h2>
        </div>
        <StatusChip status={displayStatus.replaceAll("_", " ")} compact />
      </header>
      <div className="diagnostic-grid">
        <div>
          <strong>Server snapshot</strong>
          <dl>
            <div><dt>Diagnostic status</dt><dd>{server.diagnosticStatus}</dd></div>
            <div><dt>Server observed</dt><dd>{diagnosticFact(server.serverObservedAt)}</dd></div>
            <div><dt>Governed active mode</dt><dd>{data.metadata.dataMode}</dd></div>
            <div><dt>Diagnostic active mode</dt><dd>{diagnosticFact(server.activeMode)}</dd></div>
            <div><dt>Configured mode</dt><dd>{diagnosticFact(server.configuredMode)}</dd></div>
            <div><dt>Freshness</dt><dd>{server.snapshot.freshnessStatus}</dd></div>
            <div><dt>Snapshot created</dt><dd>{diagnosticFact(server.snapshot.createdAt)}</dd></div>
            <div><dt>Maximum data date</dt><dd>{diagnosticFact(server.snapshot.maximumDataDate)}</dd></div>
            <div><dt>Snapshot age</dt><dd>{age}</dd></div>
            <div><dt>Stale after</dt><dd>{staleAfter}</dd></div>
            <div><dt>Dataset hash</dt><dd>{diagnosticFact(server.provenance.datasetHash)}</dd></div>
            <div><dt>Dataset hash basis</dt><dd>{diagnosticFact(server.provenance.datasetHashBasis)}</dd></div>
            <div><dt>Configuration hash</dt><dd>{diagnosticFact(server.provenance.configurationHash)}</dd></div>
            <div><dt>Run ID</dt><dd>{diagnosticFact(server.provenance.runId)}</dd></div>
          </dl>
        </div>
        <div>
          <strong>Client request</strong>
          <dl>
            <div><dt>Retry state</dt><dd>{retryLabel}</dd></div>
            <div><dt>Last successful request</dt><dd>{diagnosticFact(client.lastSuccessfulRequest)}</dd></div>
            <div><dt>Last attempt endpoint</dt><dd>{client.endpoint ? `/api/v1/${client.endpoint}` : "Not reported"}</dd></div>
            <div><dt>Client request ID</dt><dd>{diagnosticFact(client.clientRequestId)}</dd></div>
            <div><dt>Server request ID</dt><dd>{diagnosticFact(client.serverRequestId)}</dd></div>
            <div><dt>Response time</dt><dd>{responseTime}</dd></div>
            <div><dt>Failed endpoints</dt><dd>{client.failedEndpoints.length > 0 ? client.failedEndpoints.join(" · ") : "None"}</dd></div>
          </dl>
          {client.lastError ? (
            <p className="diagnostic-error" role="alert">
              <strong>Last error</strong>
              {client.lastError}
            </p>
          ) : null}
          {data.metadata.dataMode !== "DEMO" ? (
            <button
              type="button"
              className="secondary-button"
              onClick={onRetry}
              disabled={retryState === "RETRYING"}
            >
              {retryState === "RETRYING" ? "Retrying API…" : "Retry API"}
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}

export default function Workbench({
  initialRoute = "executive",
}: {
  initialRoute?: string;
}) {
  const [activeView, setActiveView] = useState<RouteKey>(
    resolveView(initialRoute),
  );
  const [mode, setMode] = useState<WorkbenchMode>("executive");
  const [data, setData] = useState<WorkbenchData>(getInitialWorkbenchData());
  const [filters, setFilters] = useState<GlobalFilters>(
    data.metadata.dataMode === "DEMO" ? DEFAULT_FILTERS : EMPTY_FILTERS,
  );
  const [loading, setLoading] = useState(false);
  const [unavailableReason, setUnavailableReason] = useState<string | undefined>();
  const [availableEndpoints, setAvailableEndpoints] = useState<string[]>([]);
  const [clientRequestDiagnostics, setClientRequestDiagnostics] =
    useState<ClientRequestDiagnostics>(EMPTY_CLIENT_REQUEST_DIAGNOSTICS);
  const [retryState, dispatchRetry] = useReducer(
    retryStateReducer,
    "IDLE" as RetryState,
  );
  const retryAttempt = useRef(false);
  const [evidence, setEvidence] = useState<EvidenceItem | null>(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [demoState, dispatchDemo] = useReducer(
    portfolioStoryReducer,
    INITIAL_PORTFOLIO_STORY_STATE,
  );
  const [portfolioStory, setPortfolioStory] =
    useState<PortfolioStoryRun | null>(null);
  const portfolioStoryRef = useRef<PortfolioStoryRun | null>(null);
  const [demoLaunchError, setDemoLaunchError] = useState<string | null>(null);
  const [presenterMode, setPresenterMode] = useState(false);
  const [reduceMotion, setReduceMotion] = useState(false);
  const [sampleNotice, setSampleNotice] = useState<string | null>(null);
  const appliedDemoStep = useRef(-1);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const stored = window.localStorage.getItem("naim-reduce-motion");
    const timer = window.setTimeout(
      () => setReduceMotion(stored === null ? media.matches : stored === "true"),
      0,
    );
    return () => window.clearTimeout(timer);
  }, []);

  const toggleMotion = useCallback(() => {
    setReduceMotion((current) => {
      const next = !current;
      window.localStorage.setItem("naim-reduce-motion", String(next));
      return next;
    });
  }, []);

  const togglePresenter = useCallback(() => {
    setPresenterMode((current) => !current);
  }, []);

  const navigate = useCallback(
    (view: ViewKey, replace = false) => {
      setActiveView(view);
      setMobileNav(false);
      if (typeof window !== "undefined") {
        const path = pathFor(view);
        if (replace) window.history.replaceState({}, "", path);
        else window.history.pushState({}, "", path);
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    },
    [],
  );

  useEffect(() => {
    const onPopState = () => {
      const path = window.location.pathname.replace(/^\//, "") || "start-here";
      setActiveView(resolveView(path));
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const result = await loadWorkbenchData(filters, controller.signal);
        if (!controller.signal.aborted) {
          const governedStory = portfolioStoryRef.current;
          setData(
            governedStory &&
              governedStory.activeMode === result.data.metadata.dataMode
              ? applyPortfolioStoryEvidence(result.data, governedStory)
              : result.data,
          );
          setUnavailableReason(result.unavailableReason);
          setAvailableEndpoints(result.availableEndpoints);
          setClientRequestDiagnostics(result.requestDiagnostics);
          if (result.data.metadata.dataMode === "DEMO") {
            dispatchRetry({ type: "reset" });
          } else if (
            result.data.metadata.dataMode !== "UNAVAILABLE" &&
            result.requestDiagnostics.lastSuccessfulRequest &&
            !hasCriticalRequestFailure(result.requestDiagnostics)
          ) {
            dispatchRetry({ type: "connected" });
          } else if (retryAttempt.current) {
            dispatchRetry({ type: "unavailable" });
          } else {
            dispatchRetry({ type: "reset" });
          }
          retryAttempt.current = false;
          if (
            result.data.metadata.dataMode === "DEMO" &&
            !filters.reportingMonth
          ) {
            setFilters(DEFAULT_FILTERS);
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          const reason = error instanceof Error
            ? `Validated API unavailable: ${error.message}`
            : "Validated API unavailable.";
          setData(createEmptyWorkbenchData("UNAVAILABLE", reason));
          setUnavailableReason(reason);
          setAvailableEndpoints([]);
          setClientRequestDiagnostics({
            ...EMPTY_CLIENT_REQUEST_DIAGNOSTICS,
            lastError: reason,
            failedEndpoints: ["workbench-load"],
          });
          dispatchRetry(
            retryAttempt.current ? { type: "unavailable" } : { type: "reset" },
          );
          retryAttempt.current = false;
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 180);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [filters, reloadKey]);

  const retryApi = useCallback(() => {
    if (retryState === "RETRYING") return;
    retryAttempt.current = true;
    dispatchRetry({ type: "begin" });
    setReloadKey((key) => key + 1);
  }, [retryState]);

  const demoAvailable = useMemo(
    () =>
      portfolioStoryAvailable(data.metadata.dataMode, {
        kpis: data.kpis.length,
        rootCauseLenses: data.rootCause.lenses.length,
        vintages: data.vintages.length,
        strategies: data.strategies.length,
        alerts: data.alerts.length,
        scenarios: data.scenarios.length,
      }),
    [data],
  );

  const startDemo = useCallback(async () => {
    const activeMode = data.metadata.dataMode;
    if (
      !demoAvailable ||
      (activeMode !== "DEMO" && activeMode !== "OFFLINE_SNAPSHOT")
    ) return;
    dispatchDemo({ type: "request_start" });
    setDemoLaunchError(null);
    setEvidence(null);
    appliedDemoStep.current = -1;
    try {
      const run = await runPortfolioStory(activeMode);
      portfolioStoryRef.current = run;
      setPortfolioStory(run);
      setData((current) => applyPortfolioStoryEvidence(current, run));
      setFilters((current) =>
        filtersForPortfolioStory(run, current, data.filterOptions),
      );
      setMode("recruiter");
      dispatchDemo({ type: "start", runId: run.runId, activeMode: run.activeMode });
    } catch (error) {
      dispatchDemo({ type: "start_failed" });
      const detail =
        error instanceof Error ? error.message : "The governed story service returned an unknown error.";
      const stage = error instanceof GovernedWorkflowError
        ? `${error.stage.replaceAll("_", " ")}: `
        : "";
      setDemoLaunchError(`${stage}${detail}`);
    }
  }, [data, demoAvailable]);

  const demoRunning = demoState.status === "running";
  const demoPaused = demoState.status === "paused";
  const demoComplete = demoState.status === "complete";
  const demoActive = demoRunning || demoPaused;
  const demoStep = demoState.step;
  const demoElapsed = demoState.elapsed;

  useEffect(() => {
    if (!demoRunning) return;
    const timer = window.setInterval(() => {
      dispatchDemo({ type: "tick", seconds: 0.25 });
    }, 250);
    return () => window.clearInterval(timer);
  }, [demoRunning]);

  useEffect(() => {
    if (!demoActive || appliedDemoStep.current === demoStep) return;
    appliedDemoStep.current = demoStep;
    const step = DEMO_STEPS[demoStep];
    setActiveView(step.view);
    window.history.replaceState(
      {},
      "",
      `${pathFor(step.view)}?instant-demo=1`,
    );
  }, [demoActive, demoStep]);

  const currentDemoEvidence = useMemo<EvidenceItem | null>(() => {
    if (!portfolioStory) return null;
    if (!demoComplete) return DEMO_STEPS[demoStep].evidence(data, portfolioStory);
    return {
      eyebrow: `Portfolio story evidence · ${portfolioStory.runId}`,
      title: "Governed portfolio story complete",
      summary: portfolioStory.story.whatChanged,
      facts: [
        { label: "Why", value: portfolioStory.story.why },
        { label: "Active data mode", value: portfolioStory.activeMode },
        { label: "Workspace", value: portfolioStory.workspace.name },
        { label: "Data quality", value: portfolioStory.dataQuality.status },
        { label: "Evidence", value: portfolioStory.story.evidenceProduced.join(" · ") },
        { label: "Outputs", value: portfolioStory.story.outputsAvailable.join(" · ") },
      ],
      caveat: portfolioStory.story.uncertainties.join(" · "),
      action: portfolioStory.story.supportedAction,
    };
  }, [data, demoComplete, demoStep, portfolioStory]);

  const currentNavGroup = useMemo(
    () =>
      navGroups.find((group) =>
        group.items.some((item) => item.view === activeView),
      )?.label ?? "Showcase",
    [activeView],
  );

  const openDemo = () => {
    if (!demoAvailable) return;
    setDemoLaunchError(null);
    navigate("instant-demo");
  };

  const closeDemo = () => {
    dispatchDemo({ type: "exit" });
    setEvidence(null);
    setPresenterMode(false);
    appliedDemoStep.current = -1;
    navigate("start-here", true);
  };

  const restartDemo = () => {
    dispatchDemo({ type: "restart" });
    setEvidence(null);
    appliedDemoStep.current = -1;
    setMode("recruiter");
  };

  const switchToAnalyst = () => {
    if (demoRunning) dispatchDemo({ type: "pause" });
    setPresenterMode(false);
    setMode("analyst");
  };

  const runPreparedSample = useCallback(
    (sample: PreparedSampleId) => {
      if (
        data.metadata.dataMode !== "DEMO" &&
        data.metadata.dataMode !== "OFFLINE_SNAPSHOT"
      ) return;
      const targets: Record<PreparedSampleId, ViewKey> = {
        "portfolio-deterioration": "root-cause",
        "affiliate-vintage": "vintage",
        "strategy-trade-off": "strategy",
        "fraud-alert-inflation": "alerts",
        "mild-downturn": "forecast",
      };
      const titles: Record<PreparedSampleId, string> = {
        "portfolio-deterioration": "Portfolio Deterioration",
        "affiliate-vintage": "Affiliate Vintage Weakness",
        "strategy-trade-off": "Strategy Trade-Off",
        "fraud-alert-inflation": "Fraud Alert Inflation",
        "mild-downturn": "Mild Downturn",
      };
      setMode("recruiter");
      setFilters({
        ...DEFAULT_FILTERS,
        ...(sample === "affiliate-vintage" && data.filterOptions.channels.includes("Affiliate")
          ? { channel: "Affiliate" }
          : {}),
      });
      setSampleNotice(
        `${titles[sample]} loaded from the declared ${data.metadata.dataMode} source. Open evidence on the selected analysis to inspect the governed result.`,
      );
      navigate(targets[sample]);
    },
    [data, navigate],
  );

  const updateDurableAlert = useCallback((alert: AlertRecord) => {
    setData((current) => ({
      ...current,
      alerts: current.alerts.map((item) =>
        item.id === alert.id ? alert : item,
      ),
    }));
  }, []);

  const pageProps = {
    data,
    mode,
    filters,
    portfolioStory,
    onOpenEvidence: setEvidence,
    onNavigate: navigate,
    onAlertUpdated: updateDurableAlert,
    onRefreshData: () => setReloadKey((key) => key + 1),
  };
  const knownActiveView = activeView === "not-found" ? null : activeView;
  const activeViewAvailable = knownActiveView
    ? alwaysAvailableExperienceViews.has(knownActiveView) ||
      data.metadata.availableViews.includes(knownActiveView)
    : false;
  const activeViewError = knownActiveView
    ? data.metadata.viewErrors[knownActiveView]
    : undefined;
  const apiBackedMode =
    data.metadata.dataMode === "LIVE" ||
    data.metadata.dataMode === "OFFLINE_SNAPSHOT";
  const notificationCount = activeAlertQueue(data.alerts).length;
  const lightExperience = knownActiveView
    ? chromeLightExperienceViews.has(knownActiveView)
    : false;

  return (
    <div
      className={`naim-shell ${presenterMode ? "is-presenter-mode" : ""} ${reduceMotion ? "reduce-motion" : ""} ${demoRunning || demoPaused ? `is-demo-active demo-stage-${DEMO_STEPS[demoStep].label.toLowerCase()}` : ""}`}
    >
      <a className="skip-link" href="#main-content">Skip to analysis</a>
      <button
        type="button"
        className={`mobile-nav-scrim ${mobileNav ? "is-open" : ""}`}
        onClick={() => setMobileNav(false)}
        aria-label="Close navigation"
        tabIndex={mobileNav ? 0 : -1}
      />
      <aside className={`app-sidebar ${mobileNav ? "is-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <span>n</span>
          </div>
          <div>
            <strong>nAIM</strong>
            <span>Portfolio Intelligence Workbench</span>
          </div>
        </div>
        <div className={`synthetic-label mode-${data.metadata.dataMode.toLowerCase()}`}>
          <i aria-hidden="true" />
          {data.metadata.dataMode}
        </div>
        <nav className="primary-nav" aria-label="Workbench">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-group-label">{group.label}</span>
              {group.items.map((item) => (
                <button
                  type="button"
                  key={item.view}
                  className={activeView === item.view ? "is-active" : ""}
                  aria-current={activeView === item.view ? "page" : undefined}
                  onClick={() => navigate(item.view)}
                >
                  <span className="nav-short" aria-hidden="true">{item.short}</span>
                  <span>{item.label}</span>
                  {item.badge ? <b>{item.badge}</b> : null}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <button
          type="button"
          className="instant-demo-nav"
          onClick={openDemo}
          disabled={!demoAvailable}
          title={
            demoAvailable
              ? undefined
              : "The portfolio story needs complete governed evidence in DEMO or OFFLINE_SNAPSHOT mode."
          }
        >
          <span aria-hidden="true">▶</span>
          <span>
            <strong>60-second Portfolio Story</strong>
            <small>{data.metadata.dataMode} · governed deterioration evidence</small>
          </span>
        </button>
        <div className="sidebar-foot">
          <span>Calculation version</span>
          <strong>{data.metadata.calculationVersion}</strong>
          <small>{data.metadata.runId}</small>
        </div>
      </aside>
      <div className="app-stage">
        <header className="app-topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="mobile-menu-button"
              onClick={() => setMobileNav(true)}
              aria-label="Open navigation"
            >
              ☰
            </button>
            <div className="breadcrumbs">
              <span>{currentNavGroup}</span>
              <i aria-hidden="true">/</i>
              <strong>
                {activeView === "not-found"
                  ? "Page not found"
                  : viewLabels[activeView]}
              </strong>
            </div>
          </div>
          <div className="topbar-right">
            <label className="motion-setting">
              <input
                type="checkbox"
                checked={reduceMotion}
                onChange={toggleMotion}
              />
              <span>Reduce Motion</span>
            </label>
            <SegmentedControl
              label="Workbench mode"
              value={mode}
              options={[
                { value: "executive", label: "Executive" },
                { value: "analyst", label: "Analyst" },
                { value: "recruiter", label: "Showcase" },
              ]}
              onChange={setMode}
            />
            <button
              type="button"
              className="topbar-demo-button"
              onClick={openDemo}
              disabled={!demoAvailable}
            >
              <span aria-hidden="true">▶</span>
              Portfolio story
            </button>
            {presenterMode ? (
              <button
                type="button"
                className="presenter-exit-button"
                onClick={togglePresenter}
              >
                Exit Presenter Mode
              </button>
            ) : null}
            <button
              type="button"
              className="notification-button"
              aria-label={`${notificationCount} notifications`}
              title="Open Early-Warning Alerts"
              onClick={() => navigate("alerts")}
            >
              <span aria-hidden="true">●</span>
              {notificationCount > 0 ? <b>{notificationCount}</b> : null}
            </button>
            <div className="user-chip" aria-label="Signed in as Portfolio Analyst">
              <span>PA</span>
              <div>
                <strong>Portfolio Analyst</strong>
                <small>Workbench role</small>
              </div>
            </div>
          </div>
        </header>
        {knownActiveView &&
        !lightExperience &&
        knownActiveView !== "capabilities" &&
        data.metadata.dataMode !== "UNAVAILABLE" &&
        data.filterOptions.reportingMonths.length > 0 ? (
          <GlobalFilterBar
            filters={filters}
            data={data}
            activeView={knownActiveView}
            onChange={setFilters}
            onReset={() =>
              setFilters(
                data.metadata.dataMode === "DEMO"
                  ? DEFAULT_FILTERS
                  : EMPTY_FILTERS,
              )
            }
          />
        ) : null}
        <main id="main-content" className="app-content">
          {loading && !lightExperience ? (
            <div className="refresh-progress" role="status">
              <i />
              Applying governed filters…
            </div>
          ) : null}
          {!lightExperience ? (
            <>
            <section
              className={`data-mode-banner mode-${data.metadata.dataMode.toLowerCase()}`}
              aria-label="Active data mode"
              role={data.metadata.dataMode === "UNAVAILABLE" ? "alert" : "status"}
            >
            <span className="data-mode-badge">{data.metadata.dataMode}</span>
            <div>
              <strong>
                {data.metadata.dataMode === "DEMO"
                  ? "Deterministic demonstration data"
                  : data.metadata.dataMode === "LIVE"
                    ? "Live API data"
                    : data.metadata.dataMode === "OFFLINE_SNAPSHOT"
                      ? "Verified offline API snapshot"
                      : "Portfolio data unavailable"}
              </strong>
              <p>
                {unavailableReason ??
                  data.metadata.sourceContext.reason ??
                  (data.metadata.dataMode === "DEMO"
                    ? "Declared deterministic demonstration data is active; synthetic and institution-neutral."
                    : apiBackedMode
                    ? `${availableEndpoints.length} API services passed provenance checks.`
                    : "No analytical data is active.")}
              </p>
            </div>
            {data.metadata.dataMode === "OFFLINE_SNAPSHOT" ? (
              <dl className="snapshot-provenance">
                {data.metadata.sourceContext.snapshotDate ? (
                  <div><dt>Snapshot</dt><dd>{data.metadata.sourceContext.snapshotDate}</dd></div>
                ) : null}
                {data.metadata.sourceContext.configurationHash ? (
                  <div><dt>Config hash</dt><dd>{data.metadata.sourceContext.configurationHash}</dd></div>
                ) : null}
                {data.metadata.sourceContext.datasetHash ? (
                  <div><dt>Dataset hash</dt><dd>{data.metadata.sourceContext.datasetHash}</dd></div>
                ) : null}
              </dl>
            ) : null}
            </section>
            <DiagnosticPanel
              data={data}
              client={clientRequestDiagnostics}
              retryState={retryState}
              onRetry={retryApi}
            />
            </>
          ) : null}
          {sampleNotice ? (
            <div className="sample-loaded-notice" role="status">
              <span aria-hidden="true">✓</span>
              <p>{sampleNotice}</p>
              <button type="button" onClick={() => setSampleNotice(null)} aria-label="Dismiss sample status">×</button>
            </div>
          ) : null}
          {activeView === "not-found" ? (
            <DataState
              type="error"
              title="Page not found"
              detail="This one-segment route is not part of the nAIM workbench. Use the navigation to choose an available page."
              action={
                <button type="button" className="primary-button" onClick={() => navigate("start-here")}>
                  Go to Start Here
                </button>
              }
            />
          ) : !activeViewAvailable ? (
            <DataState
              type={data.metadata.dataMode === "UNAVAILABLE" ? "error" : "empty"}
              title={`${viewLabels[activeView]} is unavailable`}
              detail={activeViewError ?? "The required API response is missing or incomplete. No demonstration values have been substituted."}
              action={
                <button
                  type="button"
                  className="primary-button"
                  onClick={retryApi}
                  disabled={retryState === "RETRYING"}
                >
                  {retryState === "RETRYING" ? "Retrying API…" : "Retry API"}
                </button>
              }
            />
          ) : activeView === "start-here" ? (
            <StartHerePage
              data={data}
              demoAvailable={demoAvailable}
              onStartDemo={() => void startDemo()}
              onRunSample={runPreparedSample}
              onNavigate={navigate}
              onEnterPresenter={() => setPresenterMode(true)}
            />
          ) : activeView === "samples" ? (
            <SamplesPage
              data={data}
              onRunSample={runPreparedSample}
              onNavigate={navigate}
            />
          ) : activeView === "how-naim" ? (
            <HowNaimPage data={data} onNavigate={navigate} />
          ) : activeView === "why-naim" ? (
            <WhyNaimPage data={data} onNavigate={navigate} />
          ) : activeView === "data-onboarding" ? (
            <DataOnboardingPage data={data} onNavigate={navigate} />
          ) : activeView === "instant-demo" ? (
            <InstantDemoLanding
              onStart={() => void startDemo()}
              data={data}
              starting={demoState.status === "starting"}
              error={demoLaunchError}
              presenterMode={presenterMode}
              reduceMotion={reduceMotion}
              onTogglePresenter={togglePresenter}
              onToggleMotion={toggleMotion}
            />
          ) : (
            <PageContent view={activeView} props={pageProps} />
          )}
          <footer className="app-footer">
            <div>
              <span>nAIM Portfolio Intelligence Workbench</span>
              <small>
                Name the movement. Own the evidence. Pronounced “name”; AIM means
                All Is Mine.
              </small>
            </div>
            <div>
              <span>Observed facts ≠ causal proof ≠ management decision</span>
              <small>Human review required for commentary and controlled responses.</small>
            </div>
          </footer>
        </main>
      </div>
      <EvidenceDrawer evidence={evidence} onClose={() => setEvidence(null)} />
      {(demoRunning || demoPaused || demoComplete) && portfolioStory ? (
        <DemoDock
          step={demoStep}
          elapsed={demoElapsed}
          running={demoRunning}
          paused={demoPaused}
          complete={demoComplete}
          story={portfolioStory.story}
          activeMode={portfolioStory.activeMode}
          presenterMode={presenterMode}
          reduceMotion={reduceMotion}
          onPause={() =>
            dispatchDemo({ type: demoPaused ? "resume" : "pause" })
          }
          onNext={() => dispatchDemo({ type: "next" })}
          onPrevious={() => dispatchDemo({ type: "previous" })}
          onSelectStep={(step) => dispatchDemo({ type: "jump", step })}
          onClose={closeDemo}
          onRestart={restartDemo}
          onOpenEvidence={() => {
            if (currentDemoEvidence) setEvidence(currentDemoEvidence);
          }}
          onAnalyst={switchToAnalyst}
          onTogglePresenter={togglePresenter}
          onToggleMotion={toggleMotion}
        />
      ) : null}
    </div>
  );
}
