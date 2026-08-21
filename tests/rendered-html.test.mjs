import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { normalizeApiOrigin } from "../app/data/api-origin.mjs";

async function render(pathname = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${pathname}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://localhost${pathname}`, {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the finished nAIM Start Here experience", async () => {
  const response = await render("/");
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>nAIM Portfolio Intelligence Workbench<\/title>/i);
  assert.match(html, /nAIM Portfolio Intelligence Workbench/);
  assert.match(html, /Name the movement\. Own the evidence\./);
  assert.match(html, /All Is Mine/);
  const retiredBrand = new RegExp(String.fromCharCode(97, 101, 103, 105, 115), "i");
  assert.doesNotMatch(html, retiredBrand);
  assert.match(html, /UNAVAILABLE/);
  assert.match(html, /Start Here/);
  assert.match(html, /What would you like to do\?/);
  assert.match(html, /Run the 60-Second Demo/);
  assert.match(html, /Define once\. Analyse consistently\. Deliver anywhere\./);
  assert.match(html, /The problem nAIM solves/);
  assert.match(html, /Governance must control/i);
  assert.match(html, /Root Cause/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/i);
  assert.doesNotMatch(html, /react-loading-skeleton/i);
});

test("every route renders its own visible data-mode and honest unavailable state", async () => {
  const checks = [
    ["/root-cause", /Root-Cause Explorer is unavailable/i],
    ["/vintage", /Vintage Explorer is unavailable/i],
    ["/strategy", /Strategy Impact Lab is unavailable/i],
    ["/alerts", /Early-Warning Alerts is unavailable/i],
    ["/model-monitoring", /Model Monitoring is unavailable/i],
    ["/market-risk", /Market Risk (?:&|&amp;) Volatility Lab is unavailable/i],
    ["/advanced-statistics", /Advanced Statistics Status is unavailable/i],
    ["/exports", /Export Centre is unavailable/i],
    ["/capabilities", /Capability Status is unavailable/i],
    ["/instant-demo", /Instant Demo is unavailable/i],
    ["/start-here", /What would you like to do\?/i],
    ["/samples", /Try a Sample/i],
    ["/how-naim", /From changing data to a reviewable decision path/i],
    ["/why-naim", /One portfolio\. Many tools/i],
    ["/data-onboarding", /Use Your Own Local Data/i],
  ];

  for (const [pathname, expected] of checks) {
    const response = await render(pathname);
    assert.equal(response.status, 200, pathname);
    const html = await response.text();
    assert.match(html, /UNAVAILABLE/, pathname);
    assert.match(html, expected, pathname);
  }
});

test("unknown one-segment routes render the framework not-found response", async () => {
  const response = await render("/definitely-not-a-workbench-route");
  assert.equal(response.status, 404);
  assert.match(await response.text(), /not found|404/i);
});

test("API base accepts an origin or a versioned URL without double prefix", () => {
  assert.equal(normalizeApiOrigin(undefined), "");
  assert.equal(normalizeApiOrigin("http://localhost:8000"), "http://localhost:8000");
  assert.equal(
    normalizeApiOrigin("http://localhost:8000/api/v1"),
    "http://localhost:8000",
  );
  assert.equal(
    normalizeApiOrigin("https://risk.example/api/v1/"),
    "https://risk.example",
  );
});

test("starter preview assets and dependency are removed", async () => {
  const [page, layout, packageJson, css] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);
  assert.match(page, /Workbench/);
  assert.match(layout, /nAIM Portfolio Intelligence Workbench/);
  assert.doesNotMatch(layout, /next\/font|Starter Project|codex-preview/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  assert.match(css, /@media \(max-width: 900px\)/);
  assert.match(css, /prefers-reduced-motion/);
  assert.match(css, /:focus-visible/);
});
