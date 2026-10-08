import { stillStartable } from "@/lib/job-id";
import type { StoredJob } from "@/lib/session";

export type OnLoad = "ask again" | "carry on" | "start" | "wait";

function askAgainOrStart(planJob: StoredJob): OnLoad {
  if (stillStartable(planJob)) {
    return "ask again";
  }

  return "start";
}

export function onLoad(plan: unknown, planJob: StoredJob | null, situation: string): OnLoad {
  if (planJob?.confirmed === false && situation) {
    return askAgainOrStart(planJob);
  }

  if (plan || planJob) {
    return "carry on";
  }

  if (situation) {
    return "start";
  }

  return "wait";
}
