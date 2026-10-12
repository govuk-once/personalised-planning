import { AgentFailure } from "./agent-failures.ts";
import { errorLogFields } from "./errors.ts";
import { failJob } from "./fail-job.ts";
import { type ClaimedJob, SOMETHING_WRONG, TOO_LARGE_TO_KEEP } from "./jobs.ts";
import { keepResult } from "./keep-result.ts";
import { type Shaped, shapeProblem } from "./outputs.ts";
import type { AgentRequest } from "./requests.ts";
import { MAX_RESULT_LENGTH } from "./results.ts";
import { askAgent } from "./turns.ts";
import type { Run } from "./worker.ts";

function ask(
  run: Run,
  request: AgentRequest,
  timeoutMs: number
): Promise<Shaped> {
  const now = new Date(run.startedMs);

  const call = {
    ...run.deps,
    sessionId: run.sessionId,
    now,
    timeoutMs,
  };

  return askAgent(run.kind, request, call);
}

export async function runJob(
  run: Run,
  job: ClaimedJob,
  request: AgentRequest,
  timeoutMs: number
): Promise<void> {
  let shaped: Shaped;

  try {
    shaped = await ask(run, request, timeoutMs);
  } catch (error) {
    if (error instanceof AgentFailure) {
      return failJob(run, error.message, error.detail);
    }

    const detail = errorLogFields(error);

    await failJob(run, SOMETHING_WRONG, detail);
    throw error;
  }

  const problem = shapeProblem(run.kind, shaped);

  if (problem) {
    return failJob(run, problem);
  }

  const text = JSON.stringify(shaped);

  if (text.length > MAX_RESULT_LENGTH) {
    const reason = TOO_LARGE_TO_KEEP[run.kind];

    return failJob(run, reason, { result_length: text.length });
  }

  await keepResult(run, job, shaped, text);
}
