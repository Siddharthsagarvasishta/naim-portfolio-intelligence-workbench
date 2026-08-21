"use client";

import type { DataMode, ViewKey, WorkbenchData } from "../workbench-types";
import { StatusChip } from "./ui";

export type PreparedSampleId =
  | "portfolio-deterioration"
  | "affiliate-vintage"
  | "strategy-trade-off"
  | "fraud-alert-inflation"
  | "mild-downturn";

interface StartExperienceProps {
  data: WorkbenchData;
  demoAvailable: boolean;
  onStartDemo: () => void;
  onRunSample: (sample: PreparedSampleId) => void;
  onNavigate: (view: ViewKey) => void;
  onEnterPresenter: () => void;
}

const TOOL_CHAIN = [
  "Financial / Risk Data",
  "SQL extraction",
  "Python / SAS",
  "Excel",
  "Power BI / Tableau",
  "PowerPoint",
  "Management Review",
];

const BREAKPOINTS = [
  "Definition drift",
  "Denominator drift",
  "Filter drift",
  "Stale data",
  "Different date cutoffs",
  "Manual adjustments",
  "Inconsistent formulas",
  "Lost assumptions",
  "Unreconciled slides",
  "Missing evidence",
];

const AUDIENCES = [
  {
    role: "Portfolio / Credit Risk Analyst",
    actions: [
      "Monitor deterioration",
      "Diagnose segments",
      "Review vintages",
      "Open investigations",
    ],
  },
  {
    role: "Fraud / Strategy Analyst",
    actions: [
      "Compare strategies",
      "Review false positives",
      "Measure friction",
      "Monitor guardrails",
    ],
  },
  {
    role: "Finance / FP&A Analyst",
    actions: [
      "Understand portfolio drivers",
      "Review profitability",
      "Compare scenarios",
      "Generate management packs",
    ],
  },
  {
    role: "Risk Manager / Executive",
    actions: [
      "Review material movement",
      "Understand evidence",
      "Review recommended investigation",
      "Download executive pack",
    ],
  },
  {
    role: "Model / Governance Reviewer",
    actions: [
      "Review definitions",
      "Inspect lineage",
      "Review uncertainty",
      "Verify versions",
    ],
  },
];

const SAMPLES: Array<{
  id: PreparedSampleId;
  title: string;
  question: string;
  method: string;
  sampleData: string;
  expected: string;
  output: string;
}> = [
  {
    id: "portfolio-deterioration",
    title: "Portfolio Deterioration",
    question: "Why did portfolio loss deteriorate?",
    method: "Governed KPI movement and exact rate decomposition",
    sampleData: "Synthetic account-month portfolio · current vs prior month",
    expected: "Reconciled mix and within-segment contribution",
    output: "Root-cause evidence and investigation path",
  },
  {
    id: "affiliate-vintage",
    title: "Affiliate Vintage Weakness",
    question: "Did acquisition growth introduce weaker portfolio quality?",
    method: "Maturity-aligned cohort comparison with confidence intervals",
    sampleData: "Affiliate vintages · months-on-book 4–8",
    expected: "Weakness concentrated in recent aligned cohorts",
    output: "Vintage evidence table and cohort view",
  },
  {
    id: "strategy-trade-off",
    title: "Strategy Trade-Off",
    question: "Did Challenger B create value after fraud, review cost and friction?",
    method: "Champion–challenger comparison with validity and guardrails",
    sampleData: "Synthetic eligible strategy population",
    expected: "Fraud benefit weighed against friction and profit",
    output: "Decision evidence and test export",
  },
  {
    id: "fraud-alert-inflation",
    title: "Fraud Alert Inflation",
    question: "Why did alerts rise faster than confirmed fraud?",
    method: "Threshold, recurrence, sample and durable lifecycle review",
    sampleData: "Governed early-warning alert queue",
    expected: "Visible signal hierarchy with controlled next action",
    output: "Alert evidence, audit history and investigation link",
  },
  {
    id: "mild-downturn",
    title: "Mild Downturn",
    question: "What happens to losses, workload and profitability under stress?",
    method: "Transparent planning scenario with versioned assumptions",
    sampleData: "Baseline and Mild Downturn projections",
    expected: "Decision-relevant loss, workload and profit differences",
    output: "Scenario comparison and assumptions evidence",
  },
];

function ToolChainVisual() {
  return (
    <section className="start-section industry-problem" id="industry-problem">
      <header className="start-section-heading">
        <div className="eyebrow">The problem nAIM solves</div>
        <h2>One portfolio. Many tools. One analytical chain to protect.</h2>
        <p>
          Finance teams already use established analytical tools. The challenge
          is preserving one trusted definition and evidence chain as recurring
          analysis moves between them.
        </p>
      </header>
      <div className="toolchain-flow" aria-label={TOOL_CHAIN.join(" to ")}>
        {TOOL_CHAIN.map((item, index) => (
          <div className="toolchain-node" key={item}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{item}</strong>
            {index < TOOL_CHAIN.length - 1 ? <i aria-hidden="true">→</i> : null}
          </div>
        ))}
      </div>
      <div className="breakpoint-panel">
        <div>
          <span className="breakpoint-mark" aria-hidden="true">!</span>
          <div>
            <strong>Where confidence can break</strong>
            <p>Every hand-off can change scope, timing, formula or evidence.</p>
          </div>
        </div>
        <ul>
          {BREAKPOINTS.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </div>
      <div className="governed-chain-proof">
        <span>nAIM preserves</span>
        <strong>Definition → Scope → Calculation → Evidence → Output</strong>
        <small>Same governed identity across review and delivery surfaces</small>
      </div>
    </section>
  );
}

function AiBoundary() {
  return (
    <section className="start-section ai-boundary">
      <header className="start-section-heading">
        <div className="eyebrow">The AI boundary</div>
        <h2>Automation and control have different jobs.</h2>
        <p>
          Automated assistance can speed up explanation and navigation. nAIM
          keeps definitions, calculations and evidence reproducible and reviewable.
        </p>
      </header>
      <div className="ai-boundary-grid">
        <article>
          <span className="boundary-label is-assist">AI can assist</span>
          <ul>
            {[
              "Explain",
              "Summarise",
              "Suggest mappings",
              "Navigate evidence",
              "Draft controlled commentary",
            ].map((item) => <li key={item}>{item}</li>)}
          </ul>
          <small>Deterministic commentary remains the V1 default.</small>
        </article>
        <article>
          <span className="boundary-label is-control">Governance must control</span>
          <ul>
            {[
              "Metric definitions",
              "Denominators",
              "Data scope",
              "Point-in-time state",
              "Assumptions",
              "Thresholds",
              "Evidence",
              "Approvals",
              "Final calculations",
            ].map((item) => <li key={item}>{item}</li>)}
          </ul>
          <small>No external AI API is required for the governed V1 workflow.</small>
        </article>
      </div>
    </section>
  );
}

function TrustStrip({ data }: { data: WorkbenchData }) {
  const context = data.metadata.sourceContext;
  return (
    <div className="start-trust-strip" aria-label="Current governed source state">
      <span><small>Data mode</small><strong>{data.metadata.dataMode}</strong></span>
      <span><small>Data quality</small><strong>{data.metadata.qualityStatus}</strong></span>
      <span><small>Reporting period</small><strong>{data.metadata.asOf}</strong></span>
      <span><small>Comparison</small><strong>{data.metadata.comparisonPeriod}</strong></span>
      <span>
        <small>Dataset binding</small>
        <strong>{context.datasetHash?.slice(0, 12) ?? "Not active"}</strong>
      </span>
    </div>
  );
}

export function StartHerePage(props: StartExperienceProps) {
  const { data, demoAvailable, onStartDemo, onNavigate, onEnterPresenter } = props;
  return (
    <div className="start-experience">
      <section className="start-hero">
        <div className="start-hero-copy">
          <div className="eyebrow">Governed portfolio intelligence</div>
          <h1>Name the movement. Own the evidence.</h1>
          <p className="start-hero-lead">
            nAIM is an independent synthetic portfolio-risk engineering project
            exploring how credit, fraud, portfolio monitoring, root-cause
            analysis, governed evidence and management reporting can be integrated
            into one reproducible analytical workflow.
          </p>
          <p className="start-hero-support">
            Define once. Analyse consistently. Deliver anywhere.
          </p>
          <p className="start-hero-disclaimer">
            Independent portfolio project · Synthetic/public demonstration data ·
            No proprietary employer data · Not a production customer-decision system
          </p>
          <div className="start-hero-actions" aria-labelledby="first-choice-title">
            <h2 id="first-choice-title">What would you like to do?</h2>
            <div>
              <button
                type="button"
                className="start-action is-primary"
                disabled={!demoAvailable}
                onClick={onStartDemo}
              >
                <span aria-hidden="true">▶</span>
                <strong>Run the 60-Second Demo</strong>
                <small>{demoAvailable ? "A guided 67-second governed story" : "Complete demo evidence is unavailable"}</small>
              </button>
              <button type="button" className="start-action" onClick={() => onNavigate("samples")}>
                <span aria-hidden="true">▦</span>
                <strong>Try a Prepared Sample</strong>
                <small>Five business questions with working analysis paths</small>
              </button>
              <button type="button" className="start-action" onClick={() => onNavigate("data-onboarding")}>
                <span aria-hidden="true">⇧</span>
                <strong>Use Your Own Local Data</strong>
                <small>Preview, map, validate and create a governed namespace</small>
              </button>
              <button type="button" className="start-action" onClick={() => onNavigate("how-naim")}>
                <span aria-hidden="true">?</span>
                <strong>Understand How nAIM Works</strong>
                <small>Follow the definition-to-output evidence chain</small>
              </button>
            </div>
          </div>
          <button type="button" className="presenter-entry" onClick={onEnterPresenter}>
            Enter Presenter Mode <span aria-hidden="true">↗</span>
          </button>
        </div>
        <aside className="start-hero-proof" aria-label="nAIM analytical workflow">
          <header>
            <span>One governed analysis run</span>
            <StatusChip status={data.metadata.dataMode} compact />
          </header>
          <ol>
            {[
              ["01", "Detect", "Name material movement"],
              ["02", "Explain", "Reconcile cause and scope"],
              ["03", "Decide", "Compare controlled alternatives"],
              ["04", "Govern", "Bind evidence and workflow"],
              ["05", "Deliver", "Carry the same facts into outputs"],
            ].map(([number, title, detail]) => (
              <li key={number}>
                <span>{number}</span>
                <div><strong>{title}</strong><small>{detail}</small></div>
              </li>
            ))}
          </ol>
          <footer>
            <strong>Observed facts ≠ causal proof ≠ management decision</strong>
            <small>Human review remains required for controlled responses.</small>
          </footer>
        </aside>
      </section>
      <TrustStrip data={data} />
      <ToolChainVisual />
      <AiBoundary />
      <section className="start-section audience-section">
        <header className="start-section-heading">
          <div className="eyebrow">Built for the review chain</div>
          <h2>One evidence base, different accountable roles.</h2>
          <p>
            nAIM complements production systems and enterprise tools; it does
            not replace their operational controls.
          </p>
        </header>
        <div className="audience-grid">
          {AUDIENCES.map((audience) => (
            <article key={audience.role}>
              <h3>{audience.role}</h3>
              <ul>{audience.actions.map((item) => <li key={item}>{item}</li>)}</ul>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

export function SamplesPage({
  data,
  onRunSample,
  onNavigate,
}: Pick<StartExperienceProps, "data" | "onRunSample" | "onNavigate">) {
  const supported = data.metadata.dataMode === "DEMO" || data.metadata.dataMode === "OFFLINE_SNAPSHOT";
  return (
    <div className="start-experience sample-experience">
      <header className="experience-page-header">
        <div>
          <div className="eyebrow">Prepared analytical workspaces</div>
          <h1>Try a Sample</h1>
          <p>
            Start with a business question, then open the existing governed
            method, evidence and output path. Sample actions never substitute
            values into an unavailable live source.
          </p>
        </div>
        <div className="experience-status">
          <small>Active source</small>
          <StatusChip status={data.metadata.dataMode} compact />
          <strong>{supported ? "Prepared samples available" : "Prepared samples require DEMO or a verified snapshot"}</strong>
        </div>
      </header>
      <div className="sample-grid">
        {SAMPLES.map((sample, index) => (
          <article className="sample-card" key={sample.id}>
            <header><span>{String(index + 1).padStart(2, "0")}</span><h2>{sample.title}</h2></header>
            <p className="sample-question">{sample.question}</p>
            <dl>
              <div><dt>Method</dt><dd>{sample.method}</dd></div>
              <div><dt>Sample data</dt><dd>{sample.sampleData}</dd></div>
              <div><dt>Expected result</dt><dd>{sample.expected}</dd></div>
              <div><dt>Available output</dt><dd>{sample.output}</dd></div>
            </dl>
            <button type="button" disabled={!supported} onClick={() => onRunSample(sample.id)}>
              Run Sample <span aria-hidden="true">→</span>
            </button>
          </article>
        ))}
      </div>
      <div className="experience-next-step">
        <div><strong>Need your own portfolio?</strong><span>Use the governed local-data onboarding path.</span></div>
        <button type="button" onClick={() => onNavigate("data-onboarding")}>Use Your Own Local Data</button>
      </div>
    </div>
  );
}

export function WhyNaimPage({ data, onNavigate }: Pick<StartExperienceProps, "data" | "onNavigate">) {
  return (
    <div className="start-experience">
      <header className="experience-page-header why-header">
        <div>
          <div className="eyebrow">Why nAIM</div>
          <h1>One portfolio. Many tools. Too many opportunities for the analytical definition to drift.</h1>
          <p>
            nAIM preserves the governed analytical chain so the same reporting
            scope, metric definition and evidence identity survive investigation,
            review and communication.
          </p>
        </div>
        <div className="experience-status">
          <small>Current evidence mode</small>
          <StatusChip status={data.metadata.dataMode} compact />
          <strong>nAIM preserves the governed analytical chain.</strong>
        </div>
      </header>
      <ToolChainVisual />
      <AiBoundary />
      <section className="value-proof-grid">
        {[
          ["Define once", "Metric definitions, units, denominators and interpretation boundaries travel together."],
          ["Analyse consistently", "Scope, point-in-time state, assumptions and thresholds are bound to the run."],
          ["Deliver anywhere", "Dashboard, Excel, PowerPoint, BI and evidence outputs retain the same governed identity."],
        ].map(([title, detail]) => <article key={title}><strong>{title}</strong><p>{detail}</p></article>)}
      </section>
      <div className="experience-next-step">
        <div><strong>See the chain in motion.</strong><span>Run the guided portfolio story from Start Here.</span></div>
        <button type="button" onClick={() => onNavigate("start-here")}>Return to Start Here</button>
      </div>
    </div>
  );
}

export function HowNaimPage({ data, onNavigate }: Pick<StartExperienceProps, "data" | "onNavigate">) {
  const stages = [
    ["01", "Scope", "Bind reporting period, comparison period, filters and data mode."],
    ["02", "Validate", "Apply data-quality publication gates and source provenance checks."],
    ["03", "Calculate", "Use versioned metric, decomposition, cohort, strategy and scenario methods."],
    ["04", "Interpret", "Separate observed movement, association, uncertainty and permitted next action."],
    ["05", "Act", "Open governed alerts and investigations with ownership and audit history."],
    ["06", "Deliver", "Generate decision-ready outputs with hashes, manifests and evidence IDs."],
  ];
  return (
    <div className="start-experience">
      <header className="experience-page-header">
        <div>
          <div className="eyebrow">How nAIM works</div>
          <h1>From changing data to a reviewable decision path.</h1>
          <p>
            Every analytical stage preserves the facts needed to reproduce,
            challenge and communicate the result.
          </p>
        </div>
        <div className="experience-status">
          <small>Current mode</small>
          <StatusChip status={data.metadata.dataMode} compact />
          <strong>{data.metadata.runId}</strong>
        </div>
      </header>
      <section className="how-flow" aria-label="nAIM governed workflow">
        {stages.map(([number, title, detail], index) => (
          <article key={number}>
            <span>{number}</span>
            <div><h2>{title}</h2><p>{detail}</p></div>
            {index < stages.length - 1 ? <i aria-hidden="true">→</i> : null}
          </article>
        ))}
      </section>
      <section className="how-evidence-contract">
        <header><div className="eyebrow">What travels with the answer</div><h2>Evidence is a product surface, not a footnote.</h2></header>
        <div>
          {[
            "Metric ID and version",
            "Formula, numerator and denominator",
            "Unit and source fields",
            "Reporting period and filters",
            "Dataset and configuration hash",
            "Evidence ID and guardrail",
            "Statistical state",
            "Permitted interpretation",
          ].map((item) => <span key={item}>{item}</span>)}
        </div>
      </section>
      <div className="experience-next-step">
        <div><strong>Ready to inspect a real path?</strong><span>Use a prepared sample or run the guided demo.</span></div>
        <div className="experience-next-actions">
          <button type="button" onClick={() => onNavigate("samples")}>Try a Sample</button>
          <button type="button" onClick={() => onNavigate("start-here")}>Start Here</button>
        </div>
      </div>
    </div>
  );
}

export function compactDataMode(mode: DataMode): string {
  if (mode === "OFFLINE_SNAPSHOT") return "Verified offline snapshot";
  if (mode === "DEMO") return "Prepared synthetic sample";
  if (mode === "LIVE") return "Live governed source";
  return "No active analytical source";
}
