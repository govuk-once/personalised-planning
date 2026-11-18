import "server-only";

import { log } from "@/lib/log";
import type { ActionResult } from "@/lib/types";

type Issue = {
  path: PropertyKey[];
  message: string;
};

type Refusal = {
  action: string;
  input: unknown;
  issues: Issue[];
  shown: string;
};

// The input failed its checks, so its session id could be any length.
const LONGEST_SESSION_ID = 128;

function sessionIdOf(input: unknown): string | undefined {
  const { sessionId } = (input ?? {}) as { sessionId?: unknown };

  if (typeof sessionId !== "string") {
    return undefined;
  }

  return sessionId.slice(0, LONGEST_SESSION_ID);
}

function reasonOf(issues: Issue[]): string {
  const [issue] = issues;

  if (!issue) {
    return "unknown";
  }

  const keys = issue.path.map(String);
  const field = keys.join(".") || "input";

  return `${field}: ${issue.message}`;
}

// Logs why a request was turned away, and what the person was shown.
export function refuse<T>(refusal: Refusal): ActionResult<T> {
  const { action, input, issues, shown } = refusal;
  const sessionId = sessionIdOf(input);
  const reason = reasonOf(issues);

  log("WARNING", "Request refused", {
    action,
    session_id: sessionId,
    reason,
    shown,
  });

  return {
    ok: false,
    error: shown,
  };
}
