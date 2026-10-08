"use server";

import {
  chatInput,
  jobLookup,
  planInput,
  type ChatInput,
  type JobLookup,
  type PlanInput,
} from "@/lib/action-input";
import { callBackend, describeFailure } from "@/lib/backend";
import { chatBody } from "@/lib/chat-request";
import { toJobRef, toJobState, UNREACHABLE, type BackendReply } from "@/lib/jobs";
import type { ActionResult, ChatTurn, JobRef, JobState, PlanResult } from "@/lib/types";

const MOCK_MODE = process.env.MOCK_MODE === "true";

const rejected = <T>(error: string): ActionResult<T> => ({ ok: false, error });

const TOO_LONG = "This conversation is too long to send. Please start again.";
const NOT_SENT = "That conversation could not be sent.";

async function ask(event: Record<string, unknown>): Promise<BackendReply> {
  try {
    return await callBackend<BackendReply>(event);
  } catch (error) {
    const detail = describeFailure(error);

    console.error("Backend call failed", {
      action: event.action,
      error: detail,
    });

    return {
      ok: false,
      error: UNREACHABLE,
    };
  }
}

export async function startChatTurn(input: ChatInput): Promise<ActionResult<JobRef>> {
  const parsed = chatInput.safeParse(input);

  if (!parsed.success) {
    const tooLong = parsed.error.issues.some(issue => issue.code === "too_big");
    const message = tooLong ? TOO_LONG : NOT_SENT;

    return rejected(message);
  }

  const { sessionId, jobId } = parsed.data;
  const body = chatBody(parsed.data);

  const reply = await ask({
    action: "start_chat",
    session_id: sessionId,
    job_id: jobId,
    ...body,
  });

  return toJobRef(reply);
}

export async function startPlan(input: PlanInput): Promise<ActionResult<JobRef>> {
  const parsed = planInput.safeParse(input);
  if (!parsed.success) return rejected("That plan request could not be sent.");

  const { sessionId, jobId, situation, userContext } = parsed.data;

  const reply = await ask({
    action: "start_plan",
    session_id: sessionId,
    job_id: jobId,
    situation,
    user_context: userContext ?? null,
    mock: MOCK_MODE,
  });

  return toJobRef(reply);
}

export async function checkJob(
  input: JobLookup
): Promise<ActionResult<JobState<ChatTurn | PlanResult>>> {
  const parsed = jobLookup.safeParse(input);

  if (!parsed.success) {
    return rejected("That request could not be checked.");
  }

  const { sessionId, jobId } = parsed.data;

  const reply = await ask({
    action: "get_job",
    session_id: sessionId,
    job_id: jobId,
  });

  return toJobState(reply);
}
