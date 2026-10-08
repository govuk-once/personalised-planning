import { type StartJob, parseApiEvent } from "./events.ts";
import { logger, type Sink } from "./log.ts";
import { lookUp } from "./look-up.ts";
import { start } from "./start.ts";
import type { Store } from "./store.ts";
import type { PublicJob } from "./views.ts";

export type WorkerPayload = {
  session_id: string;
  job_id: string;
  kind: StartJob["kind"];
  request: StartJob["request"];
};

export type ApiDeps = {
  store: Store;
  startWorker: (payload: WorkerPayload) => Promise<void>;
  nowMs: () => number;
  newId: () => string;
  log: Sink;
};

type Success = {
  ok: true;
  job: PublicJob;
};

type Refusal = {
  ok: false;
  error: string;
};

export type Reply = Success | Refusal;

export async function handle(event: unknown, deps: ApiDeps): Promise<Reply> {
  const parsed = parseApiEvent(event);

  if (!parsed.ok) {
    const log = logger(deps.log, "backend-api", "unknown");
    const fields = parsed.problems.slice(0, 10);

    log("WARNING", "Invalid event", { fields });

    return {
      ok: false,
      error: "invalid_request",
    };
  }

  if (parsed.value.action === "get_job") {
    return lookUp(parsed.value, deps);
  }

  return start(parsed.value, deps);
}
