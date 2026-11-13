"use server";

import {
  chatInput,
  jobLookup,
  planInput,
  type ChatInput,
  type JobLookup,
  type PlanInput,
} from "@/lib/action-input";
import { askBackend } from "@/lib/ask-backend";
import { chatRefusal } from "@/lib/input-limits";
import { chatBody } from "@/lib/chat-request";
import { toJobRef, toJobState } from "@/lib/jobs";
import { refuse } from "@/lib/refusal";
import type { ActionResult, ChatTurn, JobRef, JobState, PlanResult } from "@/lib/types";

const MOCK_MODE = process.env.MOCK_MODE === "true";

export async function startChatTurn(input: ChatInput): Promise<ActionResult<JobRef>> {
  const parsed = chatInput.safeParse(input);

  if (!parsed.success) {
    const message = chatRefusal(parsed.error.issues);

    return refuse({
      action: "start_chat",
      input,
      issues: parsed.error.issues,
      shown: message,
    });
  }

  const { sessionId, jobId } = parsed.data;
  const body = chatBody(parsed.data);

  const reply = await askBackend({
    action: "start_chat",
    session_id: sessionId,
    job_id: jobId,
    ...body,
  });

  return toJobRef(reply);
}

export async function startPlan(input: PlanInput): Promise<ActionResult<JobRef>> {
  const parsed = planInput.safeParse(input);

  if (!parsed.success) {
    return refuse({
      action: "start_plan",
      input,
      issues: parsed.error.issues,
      shown: "That plan request could not be sent.",
    });
  }

  const { sessionId, jobId, situation, userContext } = parsed.data;

  const reply = await askBackend({
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
    return refuse({
      action: "get_job",
      input,
      issues: parsed.error.issues,
      shown: "That request could not be checked.",
    });
  }

  const { sessionId, jobId } = parsed.data;

  const reply = await askBackend({
    action: "get_job",
    session_id: sessionId,
    job_id: jobId,
  });

  return toJobState(reply);
}
