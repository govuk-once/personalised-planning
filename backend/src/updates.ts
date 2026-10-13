import * as expressions from "./expressions.ts";
import type { Attributes, Plain } from "./items.ts";
import { namesIn, toValues, valuesIn } from "./placeholders.ts";

export type Update = {
  UpdateExpression: string;
  ConditionExpression: string;
  ExpressionAttributeNames: Record<string, string>;
  ExpressionAttributeValues: Attributes;
};

function update(
  set: string,
  condition: string,
  plain: Record<string, Plain>
): Update {
  const used = [set, condition];
  const values = valuesIn(used, plain);
  const names = namesIn(used);

  return {
    UpdateExpression: set,
    ConditionExpression: condition,
    ExpressionAttributeNames: names,
    ExpressionAttributeValues: values,
  };
}

// The claiming run may claim again, so a retry after a lost reply succeeds.
export function claim(
  runId: string,
  nowMs: number,
  startedAfterMs: number
): Update {
  const plain = {
    ":run": runId,
    ":now": nowMs,
    ":cutoff": startedAfterMs,
  };

  return update(expressions.CLAIM, expressions.CLAIMABLE, plain);
}

export function finish(
  runId: string,
  resultParts: number,
  nowMs: number
): Update {
  const plain = {
    ":run": runId,
    ":parts": resultParts,
    ":now": nowMs,
  };

  return update(expressions.FINISH, expressions.FINISHABLE, plain);
}

export function fail(error: string, nowMs: number): Update {
  const plain = {
    ":error": error,
    ":now": nowMs,
  };

  return update(expressions.FAIL, expressions.UNFINISHED, plain);
}

// Fails only a job that no Worker has claimed.
export function neverStarted(error: string, nowMs: number): Update {
  const plain = {
    ":error": error,
    ":now": nowMs,
  };

  return update(expressions.FAIL, expressions.PENDING, plain);
}

// UpdateItem, not PutItem, so the Worker needs no PutItem permission.
export function createOnce(fields: Record<string, Plain>): Update {
  const assignments: string[] = [];
  const names: Record<string, string> = {};
  const plain: Record<string, Plain> = {};

  for (const [index, field] of Object.keys(fields).entries()) {
    const name = `#f${index}`;
    const value = `:f${index}`;

    assignments.push(`${name} = ${value}`);
    names[name] = field;
    plain[value] = fields[field];
  }

  const set = assignments.join(", ");

  return {
    UpdateExpression: `SET ${set}`,
    ConditionExpression: expressions.CREATE_ONLY,
    ExpressionAttributeNames: names,
    ExpressionAttributeValues: toValues(plain),
  };
}
