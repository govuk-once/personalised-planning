import type { DynamoDBClient } from "@aws-sdk/client-dynamodb";

import { jobRecords } from "./job-records.ts";
import type { ClaimedJob, Job } from "./jobs.ts";
import { resultParts } from "./result-parts.ts";

export type Store = {
  putJob(job: Job): Promise<void>;
  getJob(sessionId: string, jobId: string): Promise<Job | null>;
  claim(
    sessionId: string,
    jobId: string,
    runId: string,
    nowMs: number
  ): Promise<ClaimedJob | null>;
  saveResult(job: ClaimedJob, parts: string[], nowMs: number): Promise<boolean>;
  fail(
    sessionId: string,
    jobId: string,
    error: string,
    nowMs: number
  ): Promise<boolean>;
  markNeverStarted(
    sessionId: string,
    jobId: string,
    error: string,
    nowMs: number
  ): Promise<boolean>;
  readResult(
    sessionId: string,
    jobId: string,
    runId: string
  ): Promise<string[]>;
};

export function createStore(client: DynamoDBClient, table: string): Store {
  const records = jobRecords(client, table);
  const parts = resultParts(client, table);

  return {
    putJob: records.putJob,
    getJob: records.getJob,
    claim: records.claim,
    fail: records.fail,
    markNeverStarted: records.markNeverStarted,
    readResult: parts.readParts,

    // Parts first, so a reader never finds a done job with a part missing.
    async saveResult(job, texts, nowMs) {
      await parts.writeParts(job, texts);

      return records.markDone(job, texts.length, nowMs);
    },
  };
}
