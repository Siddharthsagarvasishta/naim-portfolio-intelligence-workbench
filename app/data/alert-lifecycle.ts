import type {
  AlertLifecycleStatus,
  AlertLifecycleTransition,
  AlertRecord,
} from "../workbench-types";

export const ALERT_LIFECYCLE_STATUSES: readonly AlertLifecycleStatus[] = [
  "NEW",
  "ACKNOWLEDGED",
  "INVESTIGATING",
  "ACTION_PROPOSED",
  "MONITORING",
  "RESOLVED",
  "SUPPRESSED",
  "CLOSED_AS_NOISE",
];

export const ALERT_AUDIT_EVENT_TYPES = [
  "ALERT_CREATED",
  "ALERT_REPEATED",
  "ALERT_ESCALATED",
  "ALERT_ACKNOWLEDGED",
  "ALERT_SUPPRESSED",
  "ALERT_RESOLVED",
  "ALERT_REOPENED",
  "ALERT_CONDITION_CLEARED",
  "ALERT_INVESTIGATION_LINKED",
  "ALERT_STATUS_TRANSITIONED",
] as const;

export const ALERT_TRANSITION_LABELS: Record<AlertLifecycleTransition, string> = {
  ACKNOWLEDGED: "Acknowledge",
  INVESTIGATING: "Investigating",
  ACTION_PROPOSED: "Action proposed",
  MONITORING: "Monitoring",
  RESOLVED: "Resolve",
  SUPPRESSED: "Suppress",
  CLOSED_AS_NOISE: "Close as noise",
};

export function isAlertLifecycleStatus(
  value: unknown,
): value is AlertLifecycleStatus {
  return (
    typeof value === "string" &&
    ALERT_LIFECYCLE_STATUSES.includes(value as AlertLifecycleStatus)
  );
}

export function isAlertLifecycleTransition(
  value: unknown,
): value is AlertLifecycleTransition {
  return isAlertLifecycleStatus(value) && value !== "NEW";
}

export function lifecycleStatusLabel(status: AlertLifecycleStatus): string {
  return status
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (letter) => letter.toUpperCase());
}

export function activeAlertQueue(alerts: AlertRecord[]): AlertRecord[] {
  return alerts.filter((alert) =>
    alert.durable === true
      ? alert.lifecycle?.workflowActive === true
      : !["resolved", "suppressed", "closed as noise"].includes(
          alert.state.toLowerCase(),
        ),
  );
}

export function alertHistory(alerts: AlertRecord[]): AlertRecord[] {
  return alerts.filter(
    (alert) => alert.durable === true && alert.lifecycle?.workflowActive === false,
  );
}

export type AlertMutationName =
  | "ACKNOWLEDGE"
  | "START_INVESTIGATION"
  | AlertLifecycleTransition;

export type AlertMutationState =
  | { phase: "idle" }
  | {
      phase: "pending";
      alertId: string;
      mutation: AlertMutationName;
      expectedVersion: number;
    }
  | {
      phase: "success";
      alertId: string;
      mutation: AlertMutationName;
      version: number;
      message: string;
    }
  | {
      phase: "failure";
      alertId: string;
      mutation: AlertMutationName;
      message: string;
    };

export type AlertMutationReducerAction =
  | { type: "reset" }
  | {
      type: "begin";
      alertId: string;
      mutation: AlertMutationName;
      expectedVersion: number;
    }
  | {
      type: "succeeded";
      alertId: string;
      mutation: AlertMutationName;
      version: number;
      message: string;
    }
  | {
      type: "failed";
      alertId: string;
      mutation: AlertMutationName;
      message: string;
    };

export function alertMutationReducer(
  _state: AlertMutationState,
  action: AlertMutationReducerAction,
): AlertMutationState {
  switch (action.type) {
    case "reset":
      return { phase: "idle" };
    case "begin":
      // A new attempt replaces the entire prior state, clearing stale errors.
      return {
        phase: "pending",
        alertId: action.alertId,
        mutation: action.mutation,
        expectedVersion: action.expectedVersion,
      };
    case "succeeded":
      return {
        phase: "success",
        alertId: action.alertId,
        mutation: action.mutation,
        version: action.version,
        message: action.message,
      };
    case "failed":
      return {
        phase: "failure",
        alertId: action.alertId,
        mutation: action.mutation,
        message: action.message,
      };
  }
}

export function replaceWithRefreshedAlert(
  alerts: AlertRecord[],
  refreshed: AlertRecord,
  expectedVersion: number,
): AlertRecord[] {
  const lifecycle = refreshed.lifecycle;
  if (
    refreshed.durable !== true ||
    !lifecycle ||
    lifecycle.version <= expectedVersion
  ) {
    throw new Error(
      "The alert mutation did not return a newer durable alert version.",
    );
  }
  const index = alerts.findIndex((alert) => alert.id === refreshed.id);
  if (index < 0) {
    throw new Error("The refreshed durable alert was not present in the queue.");
  }
  return alerts.map((alert, itemIndex) =>
    itemIndex === index ? refreshed : alert,
  );
}
