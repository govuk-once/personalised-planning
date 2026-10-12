import type { AttributeValue } from "@aws-sdk/client-dynamodb";

import type { Job } from "./jobs.ts";
import { PARTITION_KEY, SORT_KEY } from "./table.ts";

export type Plain = string | number;
export type Attributes = Record<string, AttributeValue>;

export function jobKey(jobId: string): string {
  return `job#${jobId}`;
}

// A part's key names its run, so only the run that finished a job is read back.
export function partPrefix(jobId: string, runId: string): string {
  return `result#${jobId}#${runId}#`;
}

export function partKey(jobId: string, runId: string, index: number): string {
  const prefix = partPrefix(jobId, runId);
  const position = String(index).padStart(3, "0");

  return `${prefix}${position}`;
}

export function keyOf(sessionId: string, itemKey: string): Attributes {
  return {
    [PARTITION_KEY]: { S: sessionId },
    [SORT_KEY]: { S: itemKey },
  };
}

export function keyOfJob(sessionId: string, jobId: string): Attributes {
  const itemKey = jobKey(jobId);

  return keyOf(sessionId, itemKey);
}

export function toAttribute(value: Plain): AttributeValue {
  if (typeof value === "number") {
    const text = String(value);

    return { N: text };
  }

  return { S: value };
}

function fromAttribute(value: AttributeValue): Plain | undefined {
  if (value.N !== undefined) {
    return Number(value.N);
  }

  return value.S;
}

export function toItem(fields: Record<string, Plain | undefined>): Attributes {
  const attributes: Attributes = {};

  for (const [name, value] of Object.entries(fields)) {
    if (value !== undefined) {
      attributes[name] = toAttribute(value);
    }
  }

  return attributes;
}

export function fromItem(item: Attributes): Record<string, Plain | undefined> {
  const fields: Record<string, Plain | undefined> = {};

  for (const [name, value] of Object.entries(item)) {
    fields[name] = fromAttribute(value);
  }

  return fields;
}

export function jobItem(job: Job): Attributes {
  const itemKey = jobKey(job.job_id);

  const fields = {
    ...job,
    item_key: itemKey,
  };

  return toItem(fields);
}

export function jobFromItem(item: Attributes): Job {
  const fields = fromItem(item);

  delete fields.item_key;

  return fields as Job;
}
