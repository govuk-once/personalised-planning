"use client";

import { useEffect, useEffectEvent } from "react";

import { fetchJob } from "@/lib/fetch-job";
import { pollJob, type Outcome, type PollSettings } from "@/lib/poll";
import { getSessionId, type StoredJob } from "@/lib/session";

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

      return fetchJob<T>(sessionId, jobId);
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
