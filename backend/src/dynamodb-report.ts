import type { Call, Failure } from "./dynamodb-call.ts";
import { callSummary } from "./dynamodb-summary.ts";
import { type Level, logger, stdout } from "./log.ts";
import { PARTITION_KEY, SORT_KEY } from "./table.ts";
import { sendSubsegment } from "./xray.ts";

// The placeholders of a query
const QUERY_SESSION = ":session";
const QUERY_PREFIX = ":prefix";

function statusOf(failure: Failure | null): number {
  if (!failure) {
    return 200;
  }

  return failure.$metadata?.httpStatusCode ?? 500;
}

function report(call: Call): void {
  const { operation, input, failure, startMs } = call;
  const endMs = Date.now();
  const key = input.Key ?? input.Item ?? {};
  const values = input.ExpressionAttributeValues ?? {};
  const sessionId = key[PARTITION_KEY]?.S ?? values[QUERY_SESSION]?.S ?? "";
  const itemKey = key[SORT_KEY]?.S ?? values[QUERY_PREFIX]?.S;
  const summary = callSummary(call);
  const statusCode = statusOf(failure);
  const level: Level = failure ? "WARNING" : "INFO";
  const log = logger(stdout, "dynamodb", sessionId);

  log(level, `DynamoDB ${operation}`, {
    item_key: itemKey,
    ...summary,
    outcome: failure?.name ?? "ok",
    ms: endMs - startMs,
  });

  sendSubsegment({
    name: "DynamoDB",
    startMs,
    endMs,
    aws: {
      operation,
      table_name: input.TableName,
    },
    statusCode,
  });
}

export function reportCall(call: Call): void {
  try {
    report(call);
  } catch (error) {
    process.stderr.write(`DynamoDB call not reported: ${error}\n`);
  }
}
