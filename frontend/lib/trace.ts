import "server-only";

import { randomBytes } from "node:crypto";

import { parseTraceparent } from "@/lib/traceparent";

type RequestHeaders = { get(name: string): string | null };

export type Trace = {
  id: string;
  header: string;
};

// X-Ray writes a trace id as "1-<8 hex digits>-<24 hex digits>".
function xrayRoot(traceId: string): string {
  const epoch = traceId.slice(0, 8);
  const unique = traceId.slice(8);

  return `Root=1-${epoch}-${unique}`;
}

function browserTrace(traceparent: string | null): Trace | null {
  const parsed = parseTraceparent(traceparent);

  if (!parsed) {
    return null;
  }

  const root = xrayRoot(parsed.traceId);

  return {
    id: parsed.traceId,
    header: `${root};Parent=${parsed.parentId};Sampled=1`,
  };
}

function newTrace(): Trace {
  const seconds = Math.floor(Date.now() / 1000);
  const epoch = seconds.toString(16);
  const unique = randomBytes(12).toString("hex");
  const id = `${epoch}${unique}`;
  const root = xrayRoot(id);

  return {
    id,
    header: `${root};Sampled=1`,
  };
}

// Amplify replaces X-Amzn-Trace-Id but passes traceparent on.
export function requestTrace(headers: RequestHeaders): Trace {
  const traceparent = headers.get("traceparent");
  const browser = browserTrace(traceparent);

  return browser ?? newTrace();
}
