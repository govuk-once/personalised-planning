import type { Instrumentation } from "next";

import { log } from "@/lib/log";
import { parseTraceparent } from "@/lib/traceparent";

function digestOf(error: unknown): string | undefined {
  if (error instanceof Error && "digest" in error) {
    return String(error.digest);
  }

  return undefined;
}

function firstValue(header: string | string[] | undefined): string | undefined {
  return Array.isArray(header) ? header[0] : header;
}

export const onRequestError: Instrumentation.onRequestError = (error, request, context) => {
  const traceparent = firstValue(request.headers.traceparent);
  const trace = parseTraceparent(traceparent);
  const digest = digestOf(error);

  log("ERROR", "Request failed", {
    path: request.path,
    method: request.method,
    route: context.routePath,
    kind: context.routeType,
    error: String(error),
    digest,
    trace_id: trace?.traceId,
  });
};
