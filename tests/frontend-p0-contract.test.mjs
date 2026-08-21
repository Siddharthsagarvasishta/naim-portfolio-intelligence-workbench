import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { after, before, test } from "node:test";
import { build } from "vite";

let outputDirectory;
let p0;
let units;

before(async () => {
  outputDirectory = await mkdtemp(join(tmpdir(), "naim-p0-contract-"));
  const compile = async (name, source) => {
    const outDir = join(outputDirectory, name);
    await build({
      configFile: false,
      logLevel: "silent",
      build: {
        ssr: fileURLToPath(new URL(source, import.meta.url)),
        outDir,
        emptyOutDir: true,
        target: "node22",
        rollupOptions: { output: { entryFileNames: "entry.mjs" } },
      },
    });
    return import(`${pathToFileURL(join(outDir, "entry.mjs")).href}?test=${Date.now()}`);
  };
  [p0, units] = await Promise.all([
    compile("p0", "../app/data/p0-contract.ts"),
    compile("units", "../app/data/metric-format.ts"),
  ]);
});

after(async () => {
  if (outputDirectory) await rm(outputDirectory, { recursive: true, force: true });
});

function contribution(label) {
  return {
    label,
    contribution: 1,
    mix: 0.4,
    performance: 0.6,
    population: 100,
    persistence: 2,
    status: "Watch",
  };
}

function alert(severity, id) {
  return {
    id,
    severity,
    title: `${severity} signal`,
    metric: "Metric",
    current: "1",
    baseline: "0",
    threshold: "> 0",
    segment: "Visible segment",
    owner: "Analytics",
    state: "New",
    age: "1h",
    evidence: [],
  };
}

test("portfolio story controls support pause, resume, previous, restart, and completion", () => {
  let state = p0.portfolioStoryReducer(
    p0.INITIAL_PORTFOLIO_STORY_STATE,
    { type: "start", runId: "DEMO-1", activeMode: "OFFLINE_SNAPSHOT" },
  );
  assert.equal(state.status, "running");
  state = p0.portfolioStoryReducer(state, { type: "next" });
  assert.equal(state.step, 1);
  state = p0.portfolioStoryReducer(state, { type: "pause" });
  const pausedElapsed = state.elapsed;
  state = p0.portfolioStoryReducer(state, { type: "tick", seconds: 10 });
  assert.equal(state.elapsed, pausedElapsed);
  state = p0.portfolioStoryReducer(state, { type: "resume" });
  state = p0.portfolioStoryReducer(state, { type: "previous" });
  assert.equal(state.step, 0);
  state = p0.portfolioStoryReducer(state, {
    type: "tick",
    seconds: p0.PORTFOLIO_STORY_SECONDS,
  });
  assert.equal(state.status, "complete");
  assert.equal(state.step, p0.PORTFOLIO_STORY_STEP_COUNT - 1);
  state = p0.portfolioStoryReducer(state, { type: "restart" });
  assert.deepEqual(
    { status: state.status, step: state.step, elapsed: state.elapsed, runId: state.runId },
    { status: "running", step: 0, elapsed: 0, runId: "DEMO-1" },
  );
});

test("portfolio story eligibility includes governed offline snapshots with complete evidence", () => {
  const evidence = {
    kpis: 8,
    rootCauseLenses: 1,
    vintages: 4,
    strategies: 2,
    alerts: 2,
    scenarios: 1,
  };
  assert.equal(p0.portfolioStoryAvailable("DEMO", evidence), true);
  assert.equal(p0.portfolioStoryAvailable("OFFLINE_SNAPSHOT", evidence), true);
  assert.equal(p0.portfolioStoryAvailable("LIVE", evidence), false);
  assert.equal(p0.portfolioStoryAvailable("OFFLINE_SNAPSHOT", { ...evidence, alerts: 0 }), false);
});

test("contribution label is bound to the returned lens dimension and displayed members", () => {
  const displayed = [
    contribution("Champion A"),
    contribution("Challenger B"),
    contribution("Legacy"),
  ];
  const result = p0.resolveContributionLens(
    [
      { dimension: "Acquisition channel", total: 1, items: [contribution("Affiliate")] },
      { dimension: "Strategy", total: 1, items: displayed },
    ],
    displayed,
    "Acquisition channel",
  );
  assert.equal(result.dimension, "Strategy");
  assert.equal(result.subtitle, "Basis-point contribution by strategy");
  assert.deepEqual(result.members, ["Champion A", "Challenger B", "Legacy"]);
  assert.equal(p0.contributionDimensionMatches("Strategy", "strategy"), true);
  assert.equal(
    p0.contributionDimensionMatches("Acquisition channel", "Strategy"),
    false,
  );
});

test("early-warning headline counts the actual visible hierarchy", () => {
  assert.equal(
    p0.earlyWarningHeadline([alert("Watch", "A"), alert("Watch", "B")]),
    "0 Adverse | 2 Watch",
  );
  assert.equal(
    p0.earlyWarningHeadline([
      alert("Critical", "A"),
      alert("Adverse", "B"),
      alert("Adverse", "C"),
      alert("Watch", "D"),
    ]),
    "1 Critical · 2 Adverse · 1 Watch",
  );
});

test("all current registry units and explicit per-1,000/case semantics normalize", () => {
  const expected = {
    accounts: "count",
    annualised_rate: "percent",
    basis_points: "bps",
    currency: "currency",
    rate: "percent",
    per_1000: "per_1000",
    cases: "cases",
  };
  for (const [raw, normalized] of Object.entries(expected)) {
    assert.equal(units.normalizeMetricUnit(raw), normalized, raw);
  }
  assert.equal(units.scaleMetricValue(0.0342, "annualised_rate"), 3.42);
  assert.equal(units.scaleMetricValue(8.7, "basis_points"), 8.7);
});

test("shared KPI formatter preserves registry units and USD currency convention", () => {
  const base = {
    id: "METRIC",
    name: "Metric",
    shortName: "Metric",
    value: 0,
    prior: null,
    absoluteChange: null,
    relativeChange: null,
    denominator: "Governed denominator",
    status: "Stable",
    statisticalStatus: "Stable",
    refreshedAt: "now",
    definition: {
      formula: "governed",
      denominator: "Governed denominator",
      exclusions: "none",
      source: "registry",
      version: "v1",
    },
  };
  assert.equal(
    units.formatMetricValue({ ...base, value: 3.42, unit: "percent" }),
    "3.42%",
  );
  assert.equal(
    units.formatMetricValue({ ...base, value: 8.7, unit: "bps" }),
    "8.7 bps",
  );
  assert.equal(
    units.formatMetricValue({
      ...base,
      value: 1.9,
      unit: "per_1000",
      registryUnit: "per_1000",
      scale: "per_1000_accounts",
      formatString: "0.0 per 1,000 active accounts",
    }),
    "1.9 per 1,000 active accounts",
  );
  assert.equal(
    units.formatMetricValue({ ...base, value: 12450, unit: "cases" }),
    "12,450 cases",
  );
  assert.equal(
    units.formatMetricValue({
      ...base,
      value: 428.6,
      unit: "currency",
      currencyCode: "USD",
      currencySymbol: "$",
      scale: "adaptive_currency",
      scalingFactor: 1,
      formatString: "$0.0a;[Red]($0.0a)",
    }),
    "$428.6m",
  );
  assert.equal(
    units.formatMetricValue({
      ...base,
      value: 0.2857,
      unit: "currency",
      currencyCode: "USD",
      currencySymbol: "$",
      scale: "adaptive_currency",
      formatString: "$0.0a;[Red]($0.0a)",
    }),
    "$285.7k",
  );
  assert.equal(
    units.formatMetricValue({
      ...base,
      value: 0.000042,
      unit: "currency",
      currencyCode: "USD",
      currencySymbol: "$",
      scale: "adaptive_currency",
      formatString: "$0.0a;[Red]($0.0a)",
    }),
    "$42",
  );
  assert.equal(
    units.formatMetricValue({
      ...base,
      value: 24680,
      unit: "count",
      registryUnit: "accounts",
      formatString: "#,##0",
    }),
    "24,680 accounts",
  );
});

test("visible P0 controls are wired to governed handlers rather than decorative timers", async () => {
  const [workbench, pages] = await Promise.all([
    readFile(new URL("../app/workbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/pages.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(workbench, /Run 60-Second Portfolio Story/);
  assert.match(workbench, /runPortfolioStory\(activeMode\)/);
  for (const control of [
    "Pause",
    "Resume",
    "Next",
    "Previous",
    "Restart",
    "Open Evidence",
    "Exit Demo",
    "Switch to Analyst View",
    "Presenter Mode",
    "Reduce Motion",
  ]) {
    assert.match(workbench, new RegExp(control));
  }
  for (const question of [
    "What changed?",
    "Why?",
    "What remains uncertain?",
    "What action is supported?",
    "What evidence was produced?",
    "What outputs are available?",
  ]) {
    assert.match(workbench, new RegExp(question.replace("?", "\\?")));
  }
  assert.match(pages, /Export Executive Pack/);
  assert.match(pages, /generateExecutivePack/);
  assert.match(pages, /Download PowerPoint/);
  assert.doesNotMatch(pages, /Export Executive Pack[\s\S]{0,300}setTimeout/);
});
