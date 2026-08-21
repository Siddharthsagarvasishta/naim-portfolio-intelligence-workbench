import type {
  AlertRecord,
  ContributionPoint,
  DataMode,
  RootCauseLens,
} from "../workbench-types";

export const PORTFOLIO_STORY_SECONDS = 67;
export const PORTFOLIO_STORY_STAGE_STARTS = [0, 6, 11, 18, 27, 34, 42, 48, 54, 60] as const;
export const PORTFOLIO_STORY_STEP_COUNT = PORTFOLIO_STORY_STAGE_STARTS.length;

export type PortfolioStoryStatus =
  | "idle"
  | "starting"
  | "running"
  | "paused"
  | "complete";

export interface PortfolioStoryControlState {
  status: PortfolioStoryStatus;
  step: number;
  elapsed: number;
  runId: string | null;
  activeMode: DataMode | null;
}

export type PortfolioStoryAction =
  | { type: "request_start" }
  | { type: "start"; runId: string; activeMode: DataMode }
  | { type: "start_failed" }
  | { type: "tick"; seconds: number }
  | { type: "pause" }
  | { type: "resume" }
  | { type: "next" }
  | { type: "previous" }
  | { type: "jump"; step: number }
  | { type: "restart" }
  | { type: "exit" };

export const INITIAL_PORTFOLIO_STORY_STATE: PortfolioStoryControlState = {
  status: "idle",
  step: 0,
  elapsed: 0,
  runId: null,
  activeMode: null,
};

function elapsedForStep(step: number): number {
  return PORTFOLIO_STORY_STAGE_STARTS[
    Math.max(0, Math.min(PORTFOLIO_STORY_STEP_COUNT - 1, step))
  ];
}

function stepForElapsed(elapsed: number): number {
  let step = 0;
  PORTFOLIO_STORY_STAGE_STARTS.forEach((start, index) => {
    if (elapsed >= start) step = index;
  });
  return step;
}

export function portfolioStoryReducer(
  state: PortfolioStoryControlState,
  action: PortfolioStoryAction,
): PortfolioStoryControlState {
  if (action.type === "request_start") {
    return { ...INITIAL_PORTFOLIO_STORY_STATE, status: "starting" };
  }
  if (action.type === "start") {
    return {
      status: "running",
      step: 0,
      elapsed: 0,
      runId: action.runId,
      activeMode: action.activeMode,
    };
  }
  if (action.type === "start_failed") return INITIAL_PORTFOLIO_STORY_STATE;
  if (action.type === "exit") return INITIAL_PORTFOLIO_STORY_STATE;
  if (action.type === "restart") {
    return { ...state, status: "running", step: 0, elapsed: 0 };
  }
  if (action.type === "pause" && state.status === "running") {
    return { ...state, status: "paused" };
  }
  if (action.type === "resume" && state.status === "paused") {
    return { ...state, status: "running" };
  }
  if (action.type === "next" && state.status !== "idle") {
    if (state.step === PORTFOLIO_STORY_STEP_COUNT - 1) {
      return {
        ...state,
        status: "complete",
        elapsed: PORTFOLIO_STORY_SECONDS,
      };
    }
    const step = Math.min(PORTFOLIO_STORY_STEP_COUNT - 1, state.step + 1);
    return { ...state, step, elapsed: elapsedForStep(step) };
  }
  if (action.type === "previous" && state.status !== "idle") {
    const step = Math.max(0, state.step - 1);
    return {
      ...state,
      status: state.status === "complete" ? "paused" : state.status,
      step,
      elapsed: elapsedForStep(step),
    };
  }
  if (action.type === "jump" && state.status !== "idle") {
    const step = Math.max(
      0,
      Math.min(PORTFOLIO_STORY_STEP_COUNT - 1, Math.trunc(action.step)),
    );
    return {
      ...state,
      status: "paused",
      step,
      elapsed: elapsedForStep(step),
    };
  }
  if (action.type === "tick" && state.status === "running") {
    const elapsed = Math.min(PORTFOLIO_STORY_SECONDS, state.elapsed + action.seconds);
    return {
      ...state,
      elapsed,
      step: stepForElapsed(elapsed),
      status: elapsed >= PORTFOLIO_STORY_SECONDS ? "complete" : "running",
    };
  }
  return state;
}

export function portfolioStoryAvailable(
  mode: DataMode,
  evidence: {
    kpis: number;
    rootCauseLenses: number;
    vintages: number;
    strategies: number;
    alerts: number;
    scenarios: number;
  },
): boolean {
  return (
    (mode === "DEMO" || mode === "OFFLINE_SNAPSHOT") &&
    evidence.kpis > 0 &&
    evidence.rootCauseLenses > 0 &&
    evidence.vintages > 0 &&
    evidence.strategies > 0 &&
    evidence.alerts > 0 &&
    evidence.scenarios > 0
  );
}

function normalizedDimension(dimension: string): string {
  return dimension.trim().replaceAll("_", " ").replace(/\s+/g, " ").toLowerCase();
}

export function contributionDimensionMatches(
  lensDimension: string,
  memberDimension: string,
): boolean {
  return normalizedDimension(lensDimension) === normalizedDimension(memberDimension);
}

export function resolveContributionLens(
  lenses: RootCauseLens[],
  displayed: ContributionPoint[],
  preferredDimension: string,
): { dimension: string; subtitle: string; members: string[] } {
  const displayedMembers = displayed.map((item) => item.label);
  const displayedKey = [...displayedMembers].sort().join("\u0000");
  const matchingLens = lenses.find(
    (lens) =>
      [...lens.items.map((item) => item.label)].sort().join("\u0000") ===
      displayedKey,
  );
  const preferredLens = lenses.find(
    (lens) =>
      normalizedDimension(lens.dimension) === normalizedDimension(preferredDimension),
  );
  const dimension = matchingLens?.dimension || preferredLens?.dimension || preferredDimension;
  const normalized = normalizedDimension(dimension || "returned dimension");
  return {
    dimension,
    subtitle: `Basis-point contribution by ${normalized}`,
    members: displayedMembers,
  };
}

export function earlyWarningHeadline(alerts: AlertRecord[]): string {
  const critical = alerts.filter((alert) => alert.severity === "Critical").length;
  const adverse = alerts.filter((alert) => alert.severity === "Adverse").length;
  const watch = alerts.filter((alert) => alert.severity === "Watch").length;
  const parts: string[] = [];
  if (critical > 0) parts.push(`${critical} Critical`);
  parts.push(`${adverse} Adverse`);
  if (watch > 0 || (critical === 0 && adverse === 0)) parts.push(`${watch} Watch`);
  return parts.join(critical > 0 ? " · " : " | ");
}
