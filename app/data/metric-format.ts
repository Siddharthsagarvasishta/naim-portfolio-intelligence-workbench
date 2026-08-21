import type { KpiMetric, MetricDisplayUnit } from "../workbench-types";

export function normalizeMetricUnit(value: unknown): MetricDisplayUnit {
  const unit = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (unit === "currency") return "currency";
  if (unit === "count" || unit === "accounts" || unit === "account") return "count";
  if (unit === "cases" || unit === "case") return "cases";
  if (unit === "bps" || unit === "basis_points") return "bps";
  if (unit === "per_1000" || unit === "per-1000") return "per_1000";
  if (unit === "days" || unit === "day") return "days";
  if (unit === "months" || unit === "month") return "months";
  if (
    unit === "rate" ||
    unit === "annualised_rate" ||
    unit === "annualized_rate" ||
    unit === "percent" ||
    unit === "percentage"
  ) {
    return "percent";
  }
  return "ratio";
}

export function scaleMetricValue(value: number, rawUnit: unknown): number {
  const unit = typeof rawUnit === "string" ? rawUnit.trim().toLowerCase() : "";
  if (
    unit === "rate" ||
    unit === "annualised_rate" ||
    unit === "annualized_rate"
  ) return value * 100;
  if (unit === "currency") return value / 1_000_000;
  return value;
}

function number(value: number, maximumFractionDigits = 2): string {
  return value.toLocaleString("en-US", { maximumFractionDigits });
}

function adaptiveCurrencyFromMillions(value: number, symbol = "$"): string {
  const absolute = Math.abs(value);
  let scaled = absolute;
  let suffix = "m";
  if (absolute >= 1_000) {
    scaled = absolute / 1_000;
    suffix = "bn";
  } else if (absolute < 0.001) {
    scaled = absolute * 1_000_000;
    suffix = "";
  } else if (absolute < 1) {
    scaled = absolute * 1_000;
    suffix = "k";
  }
  const formatted = scaled.toLocaleString("en-US", {
    minimumFractionDigits: suffix ? 1 : 0,
    maximumFractionDigits: suffix ? 1 : 0,
  });
  const display = `${symbol}${formatted}${suffix}`;
  return value < 0 ? `(${display})` : display;
}

export function formatMetricNumber(
  value: number | null | undefined,
  unit: MetricDisplayUnit,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "N/A";
  if (unit === "currency") return adaptiveCurrencyFromMillions(value);
  if (unit === "percent") return `${value.toFixed(2)}%`;
  if (unit === "bps") return `${value.toFixed(1)} bps`;
  if (unit === "per_1000") return `${value.toFixed(1)} per 1,000`;
  if (unit === "cases") return `${Math.round(value).toLocaleString("en-US")} cases`;
  if (unit === "count") return `${Math.round(value).toLocaleString("en-US")} count`;
  if (unit === "days") return `${number(value)} days`;
  if (unit === "months") return `${number(value)} months`;
  return `${number(value)}×`;
}

export function formatMetricValue(
  metric: KpiMetric,
  value: number | null | undefined = metric.value,
): string {
  if (value !== null && value !== undefined && !Number.isNaN(value)) {
    if (metric.unit === "currency") {
      const symbol = metric.currencySymbol || (metric.formatString?.includes("£")
        ? "£"
        : metric.formatString?.includes("€")
          ? "€"
          : "$");
      return adaptiveCurrencyFromMillions(value, symbol);
    }
    if (metric.unit === "count") {
      const noun = metric.registryUnit === "accounts" ||
          metric.formatString?.toLowerCase().includes("accounts")
        ? "accounts"
        : metric.formatString?.toLowerCase().includes("cases")
          ? "cases"
          : "count";
      return `${Math.round(value).toLocaleString("en-US")} ${noun}`;
    }
    if (metric.unit === "per_1000") {
      const suffix = metric.scale === "per_1000_accounts" ||
          metric.formatString?.toLowerCase().includes("active accounts")
        ? " per 1,000 active accounts"
        : " per 1,000";
      return `${value.toFixed(1)}${suffix}`;
    }
  }
  return formatMetricNumber(value, metric.unit);
}

export function formatMetricDelta(metric: KpiMetric): string {
  if (metric.absoluteChange === null) return "N/A";
  const sign = metric.absoluteChange >= 0 ? "+" : "−";
  const absolute = Math.abs(metric.absoluteChange);
  if (metric.unit === "percent") return `${sign}${(absolute * 100).toFixed(0)} bps`;
  return `${sign}${formatMetricValue(metric, absolute)}`;
}
