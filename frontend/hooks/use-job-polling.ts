"use client";

import { useEffect, useEffectEvent } from "react";

import { checkJob } from "@/app/actions";
import { pollJob, type Outcome, type PollSettings } from "@/lib/poll";
import { getSessionId, type StoredJob } from "@/lib/session";
import type { ActionResult, JobState } from "@/lib/types";

export function useJobPolling<T>(
  job: StoredJob | null,
  settings: PollSettings,
  onSettled: (outcome: Outcome<T>) => void
) {
  const settle = useEffectEvent(onSettled);
  const jobId = job?.jobId;
  const startedAt = job?.startedAt ?? 0;

  useEffect(() => {
    if (!jobId) {
      return;
    }

    let cancelled = false;

    const isCancelled = () => cancelled;

    const check = () => {
      const sessionId = getSessionId();
      const reply = checkJob({
        sessionId,
        jobId,
      });

      return reply as Promise<ActionResult<JobState<T>>>;
    };

    const report = (outcome: Outcome<T> | null) => {
      if (outcome && !cancelled) {
        settle(outcome);
      }
    };

    pollJob(check, startedAt, settings, isCancelled).then(report);

    return () => {
      cancelled = true;
    };
  }, [jobId, startedAt, settings]);
}
