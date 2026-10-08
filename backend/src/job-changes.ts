import type { DynamoDBClient } from "@aws-sdk/client-dynamodb";

import { jobFromItem, keyOfJob } from "./items.ts";
import { type ClaimedJob, START_LIMIT_MS } from "./jobs.ts";
import { updater } from "./updater.ts";
import * as updates from "./updates.ts";

export function jobChanges(client: DynamoDBClient, table: string) {
  const update = updater(client, table);

  return {
    // A job the page has been told never started can no longer be claimed.
    async claim(
      sessionId: string,
      jobId: string,
      runId: string,
      nowMs: number
    ): Promise<ClaimedJob | null> {
      const startedAfterMs = nowMs - START_LIMIT_MS;
      const change = updates.claim(runId, nowMs, startedAfterMs);
      const key = keyOfJob(sessionId, jobId);
      const outcome = await update(key, change, true);

      if (!outcome.applied || !outcome.item) {
        return null;
      }

      return jobFromItem(outcome.item) as ClaimedJob;
    },

    async markDone(
      job: ClaimedJob,
      resultParts: number,
      nowMs: number
    ): Promise<boolean> {
      const change = updates.finish(job.run_id, resultParts, nowMs);
      const key = keyOfJob(job.session_id, job.job_id);
      const outcome = await update(key, change);

      return outcome.applied;
    },

    async fail(
      sessionId: string,
      jobId: string,
      error: string,
      nowMs: number
    ): Promise<boolean> {
      const key = keyOfJob(sessionId, jobId);
      const change = updates.fail(error, nowMs);
      const outcome = await update(key, change);

      return outcome.applied;
    },

    async markNeverStarted(
      sessionId: string,
      jobId: string,
      error: string,
      nowMs: number
    ): Promise<boolean> {
      const key = keyOfJob(sessionId, jobId);
      const change = updates.neverStarted(error, nowMs);
      const outcome = await update(key, change);

      return outcome.applied;
    },
  };
}
