import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { Presentation, PresentationFile } from "@oai/artifact-tool";

const WIDTH = 1280;
const HEIGHT = 720;
const C = {
  navy: "#07172d",
  ink: "#15263a",
  teal: "#00aba9",
  tealDark: "#087f7d",
  pale: "#daf7f5",
  sky: "#57b4e8",
  muted: "#5b6d80",
  line: "#cfd9e2",
  light: "#f2f6fa",
  white: "#ffffff",
  amber: "#eea12f",
  red: "#c43d4a",
  green: "#218a68",
};

function argsFrom(argv) {
  const args = {};
  for (let index = 2; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error("Arguments must be provided as --name value pairs");
    }
    args[key.slice(2)] = value;
  }
  for (const required of ["input", "output", "qa-dir", "result"]) {
    if (!args[required]) throw new Error(`Missing --${required}`);
  }
  return args;
}

async function writeBlob(destination, blob) {
  await fs.writeFile(destination, new Uint8Array(await blob.arrayBuffer()));
}

function addText(slide, name, text, position, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = String(text ?? "");
  shape.text.style = {
    fontFamily: "Aptos",
    fontSize: style.fontSize ?? 18,
    color: style.color ?? C.ink,
    bold: style.bold ?? false,
    italic: style.italic ?? false,
    alignment: style.alignment ?? "left",
    verticalAlignment: style.verticalAlignment ?? "top",
  };
  return shape;
}

function addRule(slide, name, left, top, width, color = C.line, height = 2) {
  return slide.shapes.add({
    geometry: "rect",
    name,
    position: { left, top, width, height },
    fill: color,
    line: { style: "solid", fill: "none", width: 0 },
  });
}

function monthLabel(value) {
  const match = String(value ?? "").match(/^[0-9]{4}-([0-9]{2})/);
  const labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return match ? labels[Number(match[1]) - 1] : String(value ?? "");
}

function wrappedEvidenceId(value) {
  const text = String(value ?? "");
  return text.length > 32 ? `${text.slice(0, 32)}\n${text.slice(32)}` : text;
}

function addHeader(slide, title, subtitle, index, dark = false) {
  const text = dark ? C.white : C.ink;
  const titleText = String(title ?? "");
  const titleFontSize = titleText.length > 50 ? 38 : titleText.length > 40 ? 42 : 48;
  addText(slide, `brand-${index}`, "nAIM", { left: 64, top: 28, width: 120, height: 36 }, {
    fontSize: 26,
    color: C.teal,
    bold: true,
  });
  addText(slide, `title-${index}`, titleText, { left: 64, top: 72, width: 1148, height: 66 }, {
    fontSize: titleFontSize,
    color: text,
    bold: true,
  });
  if (subtitle) {
    addText(slide, `subtitle-${index}`, subtitle, { left: 64, top: 142, width: 1148, height: 32 }, {
      fontSize: 22,
      color: dark ? "#c2d3e4" : C.muted,
    });
  }
  addRule(slide, `accent-${index}`, 64, 184, 112, C.teal, 5);
}

function addFooter(slide, model, slideIndex, dark = false) {
  const evidence = model.slide_evidence_ids[slideIndex - 1];
  const text = dark ? "#c2d3e4" : C.muted;
  const line = dark ? "#34485f" : C.line;
  addRule(slide, `footer-line-${slideIndex}`, 64, 590, 1152, line, 1);
  addText(
    slide,
    `footer-scope-${slideIndex}`,
    `Reporting: ${model.scope.reporting_period}  •  Comparison: ${model.scope.comparison_period || "N/A"}  •  Mode: ${model.data_mode}  •  Metric v${model.metric_version}`,
    { left: 64, top: 602, width: 1152, height: 22 },
    { fontSize: 12, color: text, bold: true },
  );
  addText(
    slide,
    `footer-evidence-${slideIndex}`,
    `Scope: ${model.scope.filter_scope_label}  •  Evidence: ${evidence}`,
    { left: 64, top: 628, width: 1152, height: 21 },
    { fontSize: 11, color: text },
  );
  addText(
    slide,
    `footer-synthetic-${slideIndex}`,
    `${model.synthetic_statement}  •  Refreshed: ${model.refreshed_at}`,
    { left: 64, top: 654, width: 1100, height: 20 },
    { fontSize: 10, color: text },
  );
  addText(slide, `page-${slideIndex}`, String(slideIndex).padStart(2, "0"), {
    left: 1168,
    top: 654,
    width: 48,
    height: 20,
  }, { fontSize: 10, color: text, bold: true, alignment: "right" });
}

function setNotes(slide, model, slideIndex, sources, talkTrack) {
  const evidence = model.slide_evidence_ids[slideIndex - 1];
  slide.speakerNotes.textFrame.setText(
    `${talkTrack}\n\n[Sources]\n${sources.map((item) => `- ${item}`).join("\n")}\n\n` +
      `Evidence ID: ${evidence}\nReporting period: ${model.scope.reporting_period}\n` +
      `Comparison period: ${model.scope.comparison_period || "N/A"}\n` +
      `Filter scope: ${model.scope.filter_scope_label}\nData mode: ${model.data_mode}\n` +
      `Metric version: ${model.metric_version}\nRefresh time: ${model.refreshed_at}\n` +
      `${model.synthetic_statement}`,
  );
  slide.speakerNotes.setVisible(true);
}

function addMetricStrip(slide, metrics, top = 225) {
  const selected = metrics.slice(0, 4);
  const width = 270;
  selected.forEach((metric, index) => {
    const left = 66 + index * 288;
    if (index > 0) addRule(slide, `metric-divider-${top}-${index}`, left - 18, top, 1, C.line, 120);
    addText(slide, `metric-label-${top}-${index}`, metric.name, { left, top, width, height: 42 }, {
      fontSize: 22,
      color: C.muted,
      bold: true,
    });
    addText(slide, `metric-value-${top}-${index}`, metric.display_value, { left, top: top + 48, width, height: 48 }, {
      fontSize: 31,
      color: metric.status === "adverse" ? C.red : metric.status === "favourable" ? C.green : C.ink,
      bold: true,
    });
    addText(slide, `metric-delta-${top}-${index}`, metric.display_change, { left, top: top + 99, width, height: 26 }, {
      fontSize: 22,
      color: C.muted,
    });
  });
}

function addBulletList(slide, name, items, position, options = {}) {
  const lineHeight = options.lineHeight ?? 46;
  items.forEach((item, index) => {
    const top = position.top + index * lineHeight;
    addText(slide, `${name}-marker-${index}`, options.marker ?? "•", {
      left: position.left,
      top,
      width: 28,
      height: 30,
    }, { fontSize: 20, color: options.markerColor ?? C.teal, bold: true });
    addText(slide, `${name}-item-${index}`, item, {
      left: position.left + 34,
      top,
      width: position.width - 34,
      height: lineHeight - 4,
    }, { fontSize: options.fontSize ?? 22, color: options.color ?? C.ink });
  });
}

function createDeck(model) {
  const presentation = Presentation.create({ slideSize: { width: WIDTH, height: HEIGHT } });

  // 1 — cover
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.navy;
    addText(slide, "cover-brand", "nAIM", { left: 72, top: 64, width: 180, height: 50 }, {
      fontSize: 32, color: C.teal, bold: true,
    });
    addText(slide, "cover-title", "Executive Portfolio Review", {
      left: 72, top: 190, width: 1040, height: 86,
    }, { fontSize: 68, color: C.white, bold: true });
    addText(slide, "cover-period", `${model.scope.reporting_period} versus ${model.scope.comparison_period || "N/A"}`, {
      left: 72, top: 292, width: 880, height: 42,
    }, { fontSize: 26, color: "#c2d3e4" });
    addRule(slide, "cover-accent", 72, 368, 210, C.teal, 7);
    addText(slide, "cover-tagline", "Name the movement. Own the evidence.", {
      left: 72, top: 408, width: 820, height: 50,
    }, { fontSize: 28, color: C.teal, bold: true });
    addFooter(slide, model, 1, true);
    setNotes(slide, model, 1, ["nAIM governed analytical service metadata and selected scope."],
      "Open by naming the active data mode, reporting scope and decision purpose. This is an editable evidence pack, not an automated decision.");
  }

  // 2 — status
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "Portfolio status is decision-ready", model.executive_status_subtitle, 2);
    addMetricStrip(slide, model.kpis, 228);
    addText(slide, "status-interpretation-label", "Portfolio interpretation", {
      left: 66, top: 410, width: 270, height: 32,
    }, { fontSize: 22, color: C.tealDark, bold: true });
    addText(slide, "status-interpretation", model.executive_interpretation, {
      left: 66, top: 448, width: 1110, height: 112,
    }, { fontSize: 24, color: C.ink });
    addFooter(slide, model, 2);
    setNotes(slide, model, 2, ["GET /api/v1/command-centre", "GET /api/v1/data-quality"],
      "Lead with current status, then distinguish measured movement from causal explanation.");
  }

  // 3 — KPI scorecard
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "Units and denominators are explicit", "Current value, prior value and governed comparison", 3);
    const rows = model.kpis.slice(0, 7);
    const x = [70, 455, 665, 875, 1055];
    ["Metric", "Current", "Prior", "Movement", "Denominator"].forEach((header, index) => {
      addText(slide, `kpi-header-${index}`, header, { left: x[index], top: 208, width: index === 0 ? 365 : index === 4 ? 160 : 180, height: 28 }, {
        fontSize: 22, color: C.tealDark, bold: true,
      });
    });
    addRule(slide, "kpi-header-rule", 66, 244, 1150, C.ink, 2);
    rows.forEach((metric, index) => {
      const top = 255 + index * 45;
      if (index > 0) addRule(slide, `kpi-row-rule-${index}`, 66, top - 7, 1150, C.line, 1);
      addText(slide, `kpi-name-${index}`, metric.name, { left: x[0], top, width: 365, height: 32 }, { fontSize: 20, bold: true });
      addText(slide, `kpi-current-${index}`, metric.display_value, { left: x[1], top, width: 185, height: 32 }, { fontSize: 20 });
      addText(slide, `kpi-prior-${index}`, metric.display_prior, { left: x[2], top, width: 185, height: 32 }, { fontSize: 20, color: C.muted });
      addText(slide, `kpi-movement-${index}`, metric.display_change, { left: x[3], top, width: 165, height: 28 }, {
        fontSize: 20, color: metric.status === "adverse" ? C.red : metric.status === "favourable" ? C.green : C.ink,
      });
      addText(slide, `kpi-denominator-${index}`, metric.display_denominator, { left: x[4], top, width: 160, height: 32 }, { fontSize: 17, color: C.muted });
    });
    addFooter(slide, model, 3);
    setNotes(slide, model, 3, ["GET /api/v1/kpis", "GET /api/v1/metric-registry"],
      "Use the registry unit and denominator on every row; never infer a display unit from the metric name.");
  }

  // 4 — material movements
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "Material movements focus the review", "Absolute relative magnitude is shown across units; direction remains explicit", 4);
    slide.charts.add("bar", {
      position: { left: 70, top: 210, width: 700, height: 335 },
      categories: model.movements.map((item) => item.short_name),
      series: [{ name: "Relative movement (%)", values: model.movements.map((item) => item.relative_change_pct), fill: C.teal }],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 48 },
      hasLegend: false,
      xAxis: { title: "Absolute relative movement (%)", min: 0, majorGridlines: { style: "solid", fill: C.line, width: 1 }, textStyle: { fontSize: 18, fill: C.muted } },
      yAxis: { textStyle: { fontSize: 18, fill: C.ink }, line: { style: "solid", fill: C.line, width: 1 } },
      dataLabels: { showValue: false },
    });
    addText(slide, "movement-magnitude-header", "Magnitude", { left: 724, top: 214, width: 130, height: 26 }, { fontSize: 18, color: C.tealDark, bold: true, alignment: "right" });
    model.movements.slice().reverse().forEach((item, index) => {
      addText(slide, `movement-magnitude-${index}`, item.display_magnitude, { left: 724, top: 260 + index * 54, width: 130, height: 28 }, { fontSize: 20, color: C.ink, bold: true, alignment: "right" });
    });
    addText(slide, "movements-reading", "How to read", { left: 885, top: 222, width: 280, height: 30 }, { fontSize: 24, color: C.tealDark, bold: true });
    addBulletList(slide, "movements-notes", model.movement_notes, { left: 885, top: 272, width: 310 }, { fontSize: 22, lineHeight: 70 });
    addFooter(slide, model, 4);
    setNotes(slide, model, 4, ["GET /api/v1/command-centre"],
      "Use relative movement only for prioritisation; return to each metric's native unit before interpretation.");
  }

  // 5 — trend
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "Loss-rate trend shows the governed path", "Governed monthly series through the selected reporting period", 5);
    slide.charts.add("line", {
      position: { left: 75, top: 210, width: 840, height: 350 },
      categories: model.trend.categories.map(monthLabel),
      series: [{ name: model.trend.series_name, values: model.trend.values, line: { style: "solid", fill: C.teal, width: 4 }, marker: { symbol: "circle", size: 6 } }],
      hasLegend: false,
      yAxis: { numberFormatCode: model.trend.number_format, majorGridlines: { style: "solid", fill: C.line, width: 1 }, textStyle: { fontSize: 18, fill: C.muted } },
      xAxis: { textStyle: { fontSize: 15, fill: C.muted }, line: { style: "solid", fill: C.line, width: 1 } },
    });
    addText(slide, "trend-callout-label", "Observed movement", { left: 960, top: 236, width: 230, height: 30 }, { fontSize: 22, color: C.tealDark, bold: true });
    addText(slide, "trend-callout-value", model.trend.latest_display, { left: 960, top: 278, width: 230, height: 54 }, { fontSize: 34, color: C.ink, bold: true });
    addText(slide, "trend-callout-copy", model.trend.interpretation, { left: 960, top: 350, width: 230, height: 150 }, { fontSize: 22, color: C.muted });
    addFooter(slide, model, 5);
    setNotes(slide, model, 5, ["GET /api/v1/trends", "GET /api/v1/metric-registry"],
      "Describe the observed path and comparison period. Do not call the trend a forecast.");
  }

  // 6 — root cause
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, model.root_cause.short_title, model.root_cause.subtitle, 6);
    slide.charts.add("bar", {
      position: { left: 70, top: 210, width: 650, height: 350 },
      categories: model.root_cause.categories,
      series: [{ name: "Contribution (bps)", values: model.root_cause.values, fill: C.teal }],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 42 },
      hasLegend: false,
      xAxis: { textStyle: { fontSize: 18, fill: C.ink }, line: { style: "solid", fill: C.line, width: 1 } },
      yAxis: { title: "Basis points", numberFormatCode: "0", majorGridlines: { style: "solid", fill: C.line, width: 1 }, textStyle: { fontSize: 16, fill: C.muted } },
      dataLabels: { showValue: false },
    });
    addText(slide, "root-cause-value-header", "Contribution", { left: 704, top: 214, width: 150, height: 26 }, { fontSize: 18, color: C.tealDark, bold: true, alignment: "right" });
    model.root_cause.values.slice().reverse().forEach((value, index) => {
      addText(slide, `root-cause-value-${index}`, `${Number(value).toFixed(1)} bps`, { left: 704, top: 260 + index * 55, width: 150, height: 28 }, { fontSize: 19, color: Number(value) < 0 ? C.red : C.ink, bold: true, alignment: "right" });
    });
    addText(slide, "root-cause-label", "Interpretation boundary", { left: 900, top: 224, width: 285, height: 32 }, { fontSize: 24, color: C.tealDark, bold: true });
    addText(slide, "root-cause-copy", model.root_cause.interpretation, { left: 900, top: 274, width: 285, height: 240 }, { fontSize: 22, color: C.ink });
    addFooter(slide, model, 6);
    setNotes(slide, model, 6, ["GET /api/v1/root-cause", "Exact symmetric mix/performance decomposition"],
      "Name the response dimension before naming segment contributions. Treat decomposition as associational evidence.");
  }

  // 7 — vintage
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "Vintage evidence separates maturity effects", "Latest comparable maturity points for selected cohorts", 7);
    const rows = model.vintages.slice(0, 6);
    ["Vintage", "MOB", "Observed", "30+ rate", "Cumulative loss", "Evidence note"].forEach((header, index) => {
      const lefts = [70, 240, 345, 500, 680, 875];
      addText(slide, `vintage-header-${index}`, header, { left: lefts[index], top: 214, width: index === 5 ? 320 : 155, height: 32 }, { fontSize: 22, color: C.tealDark, bold: true });
    });
    addRule(slide, "vintage-header-rule", 66, 250, 1150, C.ink, 2);
    rows.forEach((row, index) => {
      const top = 265 + index * 47;
      const values = [row.vintage, row.mob, row.observed, row.delinquency, row.loss, row.note];
      const lefts = [70, 240, 345, 500, 680, 875];
      const widths = [155, 90, 140, 160, 180, 325];
      if (index > 0) addRule(slide, `vintage-rule-${index}`, 66, top - 8, 1150, C.line, 1);
      values.forEach((value, column) => addText(slide, `vintage-${index}-${column}`, value, { left: lefts[column], top, width: widths[column], height: 32 }, { fontSize: 22, color: column === 5 ? C.muted : C.ink, bold: column === 0 }));
    });
    addFooter(slide, model, 7);
    setNotes(slide, model, 7, ["GET /api/v1/vintages"],
      "Compare cohorts only at compatible months on book and keep minimum-sample warnings visible.");
  }

  // 8 — strategy
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "Strategy trade-offs need operational guardrails", model.strategy.subtitle, 8);
    slide.charts.add("bar", {
      position: { left: 70, top: 210, width: 700, height: 350 },
      categories: model.strategy.categories,
      series: [{ name: "Expected contribution", values: model.strategy.values, fill: C.teal }],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 40 },
      hasLegend: false,
      xAxis: { textStyle: { fontSize: 18, fill: C.ink }, line: { style: "solid", fill: C.line, width: 1 } },
      yAxis: { numberFormatCode: '$0,"k"', majorGridlines: { style: "solid", fill: C.line, width: 1 }, textStyle: { fontSize: 16, fill: C.muted } },
      dataLabels: { showValue: false },
    });
    addText(slide, "strategy-value-header", "Expected profit (USD)", { left: 690, top: 214, width: 170, height: 28 }, { fontSize: 18, color: C.tealDark, bold: true, alignment: "right" });
    model.strategy.display_values.slice().reverse().forEach((value, index) => {
      addText(slide, `strategy-value-${index}`, value, { left: 710, top: 260 + index * 55, width: 150, height: 28 }, { fontSize: 20, color: C.ink, bold: true, alignment: "right" });
    });
    addText(slide, "strategy-decision-label", "Governed reading", { left: 900, top: 230, width: 280, height: 30 }, { fontSize: 24, color: C.tealDark, bold: true });
    addText(slide, "strategy-decision", model.strategy.interpretation, { left: 900, top: 278, width: 280, height: 230 }, { fontSize: 22, color: C.ink });
    addFooter(slide, model, 8);
    setNotes(slide, model, 8, ["GET /api/v1/strategy-comparison"],
      "Use strategy evidence to frame a bounded decision; do not imply randomisation where the validity block does not support it.");
  }

  // 9 — alerts
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, model.alerts.title, model.alerts.hierarchy_label, 9);
    addText(slide, "alerts-count", String(model.alerts.total), { left: 72, top: 226, width: 150, height: 70 }, { fontSize: 48, color: C.red, bold: true });
    addText(slide, "alerts-count-label", model.alerts.count_label, { left: 72, top: 300, width: 180, height: 30 }, { fontSize: 22, color: C.muted });
    addBulletList(slide, "alerts-list", model.alerts.items, { left: 310, top: 212, width: 845 }, { fontSize: 18, lineHeight: 52, marker: "→", markerColor: C.red });
    addText(slide, "alerts-boundary", model.alerts.boundary, { left: 72, top: 492, width: 1080, height: 68 }, { fontSize: 20, color: C.ink, italic: true });
    addFooter(slide, model, 9);
    setNotes(slide, model, 9, ["GET /api/v1/alerts", "GET /api/v1/root-cause"],
      "Reconcile the headline count to the response rows before discussing severity or ownership.");
  }

  // 10 — scenario
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "Mild Downturn quantifies planning impact", model.scenario.subtitle, 10);
    slide.charts.add("line", {
      position: { left: 70, top: 210, width: 830, height: 350 },
      categories: model.scenario.categories.map(monthLabel),
      series: model.scenario.series,
      hasLegend: true,
      legend: { position: "bottom", overlay: false, textStyle: { fontSize: 18, fill: C.muted } },
      yAxis: { numberFormatCode: "$#,##0", majorGridlines: { style: "solid", fill: C.line, width: 1 }, textStyle: { fontSize: 18, fill: C.muted } },
      xAxis: { textStyle: { fontSize: 15, fill: C.muted }, line: { style: "solid", fill: C.line, width: 1 } },
    });
    addText(slide, "scenario-implication-label", "Implication", { left: 950, top: 228, width: 230, height: 32 }, { fontSize: 24, color: C.tealDark, bold: true });
    addText(slide, "scenario-implication", model.scenario.interpretation, { left: 950, top: 278, width: 230, height: 240 }, { fontSize: 22, color: C.ink });
    addFooter(slide, model, 10);
    setNotes(slide, model, 10, ["GET /api/v1/scenarios"],
      "State the assumptions and limitation before discussing the projected difference from baseline.");
  }

  // 11 — investigation
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "Priority investigation creates accountable work", model.investigation.status_line, 11);
    addText(slide, "investigation-question-label", "Business question", { left: 72, top: 220, width: 280, height: 32 }, { fontSize: 24, color: C.tealDark, bold: true });
    addText(slide, "investigation-question", model.investigation.business_question, { left: 72, top: 270, width: 660, height: 104 }, { fontSize: 26, color: C.ink, bold: true });
    addText(slide, "investigation-hypothesis-label", "Testable hypothesis", { left: 72, top: 412, width: 280, height: 32 }, { fontSize: 24, color: C.tealDark, bold: true });
    addText(slide, "investigation-hypothesis", model.investigation.hypothesis, { left: 72, top: 458, width: 660, height: 90 }, { fontSize: 22, color: C.ink });
    addRule(slide, "investigation-divider", 790, 220, 1, C.line, 320);
    addText(slide, "investigation-evidence-label", "Evidence ID", { left: 830, top: 226, width: 350, height: 26 }, { fontSize: 18, color: C.tealDark, bold: true });
    addText(slide, "investigation-evidence", wrappedEvidenceId(model.investigation.evidence_id), { left: 830, top: 256, width: 350, height: 54 }, { fontSize: 14, color: C.ink });
    addText(slide, "investigation-metric-label", "Affected metric", { left: 830, top: 320, width: 350, height: 26 }, { fontSize: 18, color: C.tealDark, bold: true });
    addText(slide, "investigation-metric-name", model.investigation.affected_metric_name, { left: 830, top: 350, width: 350, height: 32 }, { fontSize: 22, color: C.ink, bold: true });
    addText(slide, "investigation-metric-id", model.investigation.affected_metric_id, { left: 830, top: 384, width: 350, height: 26 }, { fontSize: 16, color: C.muted });
    addText(slide, "investigation-approval-label", "Approval state", { left: 830, top: 426, width: 350, height: 26 }, { fontSize: 18, color: C.tealDark, bold: true });
    addText(slide, "investigation-approval", model.investigation.approval_state, { left: 830, top: 456, width: 350, height: 30 }, { fontSize: 22, color: C.ink, bold: true });
    addText(slide, "investigation-boundary", model.investigation.decision_boundary, { left: 830, top: 502, width: 350, height: 46 }, { fontSize: 18, color: C.muted, italic: true });
    addFooter(slide, model, 11);
    setNotes(slide, model, 11, ["Governed investigation workflow record", "GET /api/v1/investigations"],
      "Confirm owner, status, evidence ID and approval boundary before agreeing the next action.");
  }

  // 12 — actions
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "Actions stay reviewable and approval-bound", "Analytical evidence supports a decision process; it does not execute one", 12);
    model.actions.forEach((action, index) => {
      const top = 210 + index * 88;
      addText(slide, `action-number-${index}`, String(index + 1).padStart(2, "0"), { left: 72, top, width: 70, height: 40 }, { fontSize: 24, color: C.teal, bold: true });
      addText(slide, `action-title-${index}`, action.title, { left: 160, top, width: 250, height: 36 }, { fontSize: 21, color: C.ink, bold: true });
      addText(slide, `action-copy-${index}`, action.description, { left: 420, top, width: 565, height: 62 }, { fontSize: 21, color: C.ink });
      addText(slide, `action-owner-${index}`, action.owner, { left: 1010, top, width: 185, height: 40 }, { fontSize: 22, color: C.muted, bold: true, alignment: "right" });
      if (index < model.actions.length - 1) addRule(slide, `action-rule-${index}`, 160, top + 66, 1035, C.line, 1);
    });
    addFooter(slide, model, 12);
    setNotes(slide, model, 12, ["Governed investigation and approval workflow contracts"],
      "End the decision discussion with named ownership and the approval required for any change.");
  }

  // 13 — data quality
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "Data quality passes—with explicit limitations", model.data_quality.subtitle, 13);
    addText(slide, "dq-status", model.data_quality.status, { left: 72, top: 222, width: 230, height: 70 }, { fontSize: 48, color: model.data_quality.status === "PASS" ? C.green : C.amber, bold: true });
    addText(slide, "dq-score", `${model.data_quality.score_display} quality score`, { left: 72, top: 300, width: 270, height: 32 }, { fontSize: 22, color: C.muted });
    addBulletList(slide, "dq-checks", model.data_quality.items, { left: 390, top: 220, width: 770 }, { fontSize: 22, lineHeight: 58 });
    addText(slide, "dq-limitations-label", "Limitations", { left: 72, top: 408, width: 260, height: 32 }, { fontSize: 24, color: C.tealDark, bold: true });
    addText(slide, "dq-limitations", model.data_quality.limitations, { left: 72, top: 454, width: 1080, height: 96 }, { fontSize: 22, color: C.ink });
    addFooter(slide, model, 13);
    setNotes(slide, model, 13, ["GET /api/v1/data-quality", "Pipeline publication manifest"],
      "Separate a passed publication gate from model, causal and scenario limitations.");
  }

  // 14 — methodology
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "Methodology is transparent and reproducible", "Calculation, scope and interpretation contracts", 14);
    addText(slide, "method-left-label", "Calculation system", { left: 72, top: 218, width: 430, height: 34 }, { fontSize: 24, color: C.tealDark, bold: true });
    addBulletList(slide, "method-left", model.methodology.calculation, { left: 72, top: 270, width: 500 }, { fontSize: 22, lineHeight: 66 });
    addRule(slide, "method-divider", 626, 218, 1, C.line, 330);
    addText(slide, "method-right-label", "Interpretation boundary", { left: 682, top: 218, width: 430, height: 34 }, { fontSize: 24, color: C.tealDark, bold: true });
    addBulletList(slide, "method-right", model.methodology.boundaries, { left: 682, top: 270, width: 500 }, { fontSize: 22, lineHeight: 66, markerColor: C.amber });
    addFooter(slide, model, 14);
    setNotes(slide, model, 14, ["GET /api/v1/metric-registry", "nAIM calculation modules", "Artifact manifest and reconciliation block"],
      "Use this appendix to answer formula, denominator, version, source and limitation questions.");
  }

  return presentation;
}

async function main() {
  const args = argsFrom(process.argv);
  const model = JSON.parse(await fs.readFile(args.input, "utf8"));
  await fs.mkdir(path.dirname(args.output), { recursive: true });
  await fs.mkdir(args["qa-dir"], { recursive: true });

  const presentation = createDeck(model);
  const slideResults = [];
  for (const [index, slide] of presentation.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    const pngPath = path.join(args["qa-dir"], `${stem}.png`);
    const layoutPath = path.join(args["qa-dir"], `${stem}.layout.json`);
    await writeBlob(pngPath, await presentation.export({ slide, format: "png", scale: 1 }));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(layoutPath, await layout.text(), "utf8");
    slideResults.push({ slide_number: index + 1, png: pngPath, layout: layoutPath });
  }
  await writeBlob(
    path.join(args["qa-dir"], "deck-montage.webp"),
    await presentation.export({ format: "webp", montage: true, scale: 1 }),
  );
  const snapshot = await presentation.inspect({
    kind: "slide,textbox,shape,chart,notes",
    maxChars: 200000,
  });
  await fs.writeFile(path.join(args["qa-dir"], "deck-inspect.ndjson"), snapshot.ndjson, "utf8");

  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(args.output);
  await fs.writeFile(
    args.result,
    JSON.stringify({
      status: "PASS",
      slide_count: presentation.slides.items.length,
      slides: slideResults,
      montage: path.join(args["qa-dir"], "deck-montage.webp"),
      inspect: path.join(args["qa-dir"], "deck-inspect.ndjson"),
    }, null, 2) + "\n",
    "utf8",
  );
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
