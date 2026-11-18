import "server-only";

import { headers } from "next/headers";

import { callBackend, describeFailure } from "@/lib/backend";
import { UNREACHABLE, type BackendReply } from "@/lib/jobs";
import { log } from "@/lib/log";
import { requestTrace } from "@/lib/trace";

type BackendEvent = Record<string, unknown>;

const POLL = "get_job";

export async function askBackend(event: BackendEvent): Promise<BackendReply> {
  const requestHeaders = await headers();
  const trace = requestTrace(requestHeaders);
  const startedMs = Date.now();

  const fields = {
    action: event.action,
    session_id: event.session_id,
    job_id: event.job_id,
    trace_id: trace.id,
  };

  try {
    const reply = await callBackend<BackendReply>(event, trace.header);

    if (event.action !== POLL) {
      const ms = Date.now() - startedMs;
      const refused = reply.ok ? undefined : reply.error;

      log("INFO", "Backend called", {
        ...fields,
        ms,
        refused,
      });
    }

    return reply;
  } catch (error) {
    const detail = describeFailure(error);

    log("ERROR", "Backend call failed", {
      ...fields,
      error: detail,
    });

    return {
      ok: false,
      error: UNREACHABLE,
    };
  }
}
