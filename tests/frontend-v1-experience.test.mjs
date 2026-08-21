import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { after, before, test } from "node:test";
import { build } from "vite";

let outputDirectory;
let p0;
let charts;

before(async () => {
  outputDirectory = await mkdtemp(join(tmpdir(), "naim-v1-experience-"));
  const compile = async (name, source) => {
    const outDir = join(outputDirectory, name);
    await build({
      configFile: false,
      logLevel: "silent",
      ssr: { noExternal: ["react", "react/jsx-runtime"] },
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
  [p0, charts] = await Promise.all([
    compile("p0", "../app/data/p0-contract.ts"),
    compile("charts", "../app/components/charts.tsx"),
  ]);
});

after(async () => {
  if (outputDirectory) await rm(outputDirectory, { recursive: true, force: true });
});

test("guided story uses the governed ten-stage 67-second timeline and clickable jumps pause", () => {
  assert.equal(p0.PORTFOLIO_STORY_SECONDS, 67);
  assert.equal(p0.PORTFOLIO_STORY_STEP_COUNT, 10);
  assert.deepEqual([...p0.PORTFOLIO_STORY_STAGE_STARTS], [0, 6, 11, 18, 27, 34, 42, 48, 54, 60]);

  let state = p0.portfolioStoryReducer(p0.INITIAL_PORTFOLIO_STORY_STATE, {
    type: "start",
    runId: "DEMO-V1",
    activeMode: "DEMO",
  });
  state = p0.portfolioStoryReducer(state, { type: "jump", step: 6 });
  assert.deepEqual(
    { status: state.status, step: state.step, elapsed: state.elapsed },
    { status: "paused", step: 6, elapsed: 42 },
  );
  state = p0.portfolioStoryReducer(state, { type: "resume" });
  state = p0.portfolioStoryReducer(state, { type: "tick", seconds: 6 });
  assert.equal(state.step, 7);
  assert.equal(state.status, "running");
});

test("chart CSV export preserves negative numbers and neutralizes spreadsheet formulas", () => {
  const csv = charts.chartRowsToCsv([
    { label: "Movement", value: -7.3, note: "=HYPERLINK(\"bad\")" },
    { label: "Stable", value: 4.2, note: "reviewed" },
  ]);
  assert.match(csv, /"-7\.3"/);
  assert.match(csv, /"'=HYPERLINK\(""bad""\)"/);
  assert.match(csv, /"reviewed"/);
});

test("first-time routes, samples, onboarding and presenter controls are real wired surfaces", async () => {
  const [workbench, startPages, onboardingPage, onboardingClient, routes, home] = await Promise.all([
    readFile(new URL("../app/workbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/start-pages.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/onboarding-page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/data/onboarding-client.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/[view]/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(home, /initialRoute="start-here"/);
  for (const route of ["start-here", "samples", "how-naim", "why-naim", "data-onboarding", "executive"]) {
    assert.match(routes, new RegExp(`"${route}"`));
  }
  for (const group of ["START", "MONITOR", "DIAGNOSE", "DECIDE", "GOVERN", "DELIVER"]) {
    assert.match(workbench, new RegExp(`label: "${group}"`));
  }
  for (const stage of ["Problem", "Trust", "Movement", "Cause", "Vintage", "Strategy", "Warning", "Scenario", "Action", "Outputs"]) {
    assert.match(workbench, new RegExp(`label: "${stage}"`));
  }
  assert.match(workbench, /type: "jump"/);
  assert.match(workbench, /Enter Presenter Mode/);
  assert.match(workbench, /Reduce Motion/);
  assert.match(
    workbench,
    /setFilters\(\{\s*\.\.\.DEFAULT_FILTERS,[\s\S]{0,220}sample === "affiliate-vintage"/,
  );
  assert.doesNotMatch(
    workbench,
    /data\.metadata\.dataMode === "DEMO" \? DEFAULT_FILTERS : current/,
  );

  assert.match(startPages, /Name the movement\. Own the evidence\./);
  assert.match(startPages, /Define once\. Analyse consistently\. Deliver anywhere\./);
  for (const sample of [
    "Portfolio Deterioration",
    "Affiliate Vintage Weakness",
    "Strategy Trade-Off",
    "Fraud Alert Inflation",
    "Mild Downturn",
  ]) {
    assert.match(startPages, new RegExp(sample));
  }
  assert.match(startPages, /onRunSample\(sample\.id\)/);

  for (const step of [
    "Choose local data",
    "Preview",
    "Select data contract",
    "Map fields",
    "Validate",
    "Review issues",
    "Create governed snapshot",
    "Select analysis",
    "Run",
    "Review evidence",
    "Export",
  ]) {
    assert.match(onboardingPage, new RegExp(step));
  }
  for (const endpoint of [
    "data-onboarding/contracts",
    "data-onboarding/sources/upload",
    "data-onboarding/preview",
    "data-onboarding/map",
    "data-onboarding/validate",
    "data-onboarding/profiles",
    "data-onboarding/load",
  ]) {
    assert.match(onboardingClient, new RegExp(endpoint.replaceAll("/", "\\/")));
  }
});

test("the reusable chart interaction frame is applied to all six review surfaces", async () => {
  const [chartsSource, pages] = await Promise.all([
    readFile(new URL("../app/components/charts.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/pages.tsx", import.meta.url), "utf8"),
  ]);
  for (const control of ["Open evidence", "Download chart data", "Drill through"]) {
    assert.match(chartsSource, new RegExp(control));
  }
  assert.match(chartsSource, /rangeOptions/);
  assert.match(chartsSource, /chart-series-controls/);
  const uses = pages.match(/<ChartInteractionFrame/g) ?? [];
  assert.ok(uses.length >= 6, `expected at least six interactive chart surfaces, found ${uses.length}`);
});

test("visible V1 actions execute or are explicitly labelled read-only", async () => {
  const [workbench, pages, startPages, packageJson, styles] = await Promise.all([
    readFile(new URL("../app/workbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/pages.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/start-pages.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(pages, /Export queued|DownloadAction/);
  assert.doesNotMatch(pages, /<button type="button" key=\{title\}>/);
  assert.doesNotMatch(pages, /durable[^\n]{0,80}not implemented/i);
  assert.match(pages, /Read-only definitions/);
  assert.match(pages, /Documentation only/);
  assert.match(
    workbench,
    /className="notification-button"[\s\S]{0,260}onClick=\{\(\) => navigate\("alerts"\)\}/,
  );
  assert.match(startPages, /Independent portfolio project/);
  assert.match(startPages, /No proprietary employer data/);
  assert.match(startPages, /Not a production customer-decision system/);
  assert.match(styles, /\.data-mode-banner \{ align-items: flex-start; flex-wrap: wrap; \}/);
  assert.match(styles, /\.snapshot-provenance \{ grid-template-columns: 1fr; \}/);
  assert.equal(JSON.parse(packageJson).scripts.test, "npm run build && node --test tests/*.test.mjs");
});
