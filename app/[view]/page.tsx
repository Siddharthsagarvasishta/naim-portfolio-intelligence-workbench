import Workbench from "../workbench";
import { notFound } from "next/navigation";

const WORKBENCH_VIEWS = new Set([
  "start-here",
  "samples",
  "how-naim",
  "why-naim",
  "data-onboarding",
  "executive",
  "trends",
  "root-cause",
  "vintage",
  "strategy",
  "partners",
  "vendors",
  "membership",
  "baskets",
  "finance",
  "market-risk",
  "advanced-statistics",
  "data-quality",
  "forecast",
  "alerts",
  "investigations",
  "model-monitoring",
  "methodology",
  "exports",
  "capabilities",
  "instant-demo",
]);

export default async function WorkbenchView({
  params,
}: {
  params: Promise<{ view: string }>;
}) {
  const { view } = await params;
  if (!WORKBENCH_VIEWS.has(view)) notFound();
  return <Workbench initialRoute={view} />;
}
