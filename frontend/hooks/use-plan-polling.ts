"use client";

import { useJobPolling } from "@/hooks/use-job-polling";
import type { Outcome, PollSettings } from "@/lib/poll";
import { clearPlanJob, savePlan, type StoredJob } from "@/lib/session";
import type { PlanResult } from "@/lib/types";

const NO_PLAN = "The planner did not return a plan. Try starting again.";

type SetError = (error: string | null) => void;

export function usePlanPolling(
  planJob: StoredJob | null,
  settings: PollSettings,
  setError: SetError
) {
  function settle(outcome: Outcome<PlanResult>) {
    if (!outcome.ok) {
      if (!outcome.keepJob) {
        clearPlanJob();
      }

      setError(outcome.error);
      return;
    }

    const finished = outcome.result.plan;

    if (!finished) {
      clearPlanJob();
      setError(NO_PLAN);
      return;
    }

    savePlan(finished);
    clearPlanJob();
  }

  const confirmedJob = planJob?.confirmed === false ? null : planJob;

  useJobPolling<PlanResult>(confirmedJob, settings, settle);
}
