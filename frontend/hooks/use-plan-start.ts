"use client";

import { useCallback, useTransition } from "react";

import { startPlan } from "@/app/actions";
import { SITE_UPDATED, startTwice } from "@/lib/action-failure";
import { freshJob } from "@/lib/job-id";
import { undoUnlessLeaving } from "@/lib/page-lifecycle";
import { clearPlanJob, getSessionId, savePlanJob, type StoredJob } from "@/lib/session";

type SetError = (error: string | null) => void;
type UserContext = Record<string, unknown>;

async function askForPlan(
  job: StoredJob,
  brief: string,
  userContext: UserContext,
  setError: SetError
) {
  setError(null);

  const sessionId = getSessionId();
  const request = {
    sessionId,
    jobId: job.jobId,
    situation: brief,
    userContext,
  };
  const started = await startTwice(() => startPlan(request));

  if (started.ok) {
    const confirmed = {
      ...job,
      confirmed: true,
    };

    savePlanJob(confirmed);
    return;
  }

  if (started.error === SITE_UPDATED) {
    // A reload asks for this job again.
    setError(started.error);
    return;
  }

  undoUnlessLeaving(() => {
    clearPlanJob();
    setError(started.error);
  });
}

export function usePlanStart(setError: SetError) {
  const [starting, startStarting] = useTransition();

  const generate = useCallback(
    (brief: string, userContext: UserContext, job: StoredJob = freshJob("plan")) => {
      savePlanJob(job);
      startStarting(() => askForPlan(job, brief, userContext, setError));
    },
    [setError]
  );

  return {
    starting,
    generate,
  };
}
