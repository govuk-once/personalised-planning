"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { useChatPolling } from "@/hooks/use-chat-polling";
import { useChatStart } from "@/hooks/use-chat-start";
import { useShownError } from "@/hooks/use-shown-error";
import { withUserMessage } from "@/lib/conversation";
import { freshJob } from "@/lib/job-id";
import { track } from "@/lib/monitoring";
import {
  clearSession,
  getSessionId,
  saveChatJob,
  saveConversation,
  useChatJob,
  useConversation,
} from "@/lib/session";

const CHAT_POLLING = {
  intervalMs: 5_000,
  timeoutMs: 600_000,
  missWindowMs: 60_000,
};

export function useIntake() {
  const router = useRouter();
  const conversation = useConversation();
  const chatJob = useChatJob();
  const [draft, setDraft] = useState("");
  const [error, setError] = useShownError("chat");

  const feedback = {
    setDraft,
    setError,
  };
  const { begin, abandon } = useChatStart(conversation, chatJob, feedback);

  const handlers = {
    abandon,
    setError,
  };
  useChatPolling(chatJob, conversation, CHAT_POLLING, handlers);

  function send(text: string) {
    const trimmed = text.trim();

    if (!trimmed || chatJob) {
      return;
    }

    const fresh = freshJob("chat");
    const job = {
      ...fresh,
      text: trimmed,
    };
    const withUser = withUserMessage(conversation, trimmed);

    setError(null);
    setDraft("");
    saveConversation(withUser);
    saveChatJob(job);
    getSessionId();

    track("message_sent", {
      job_id: job.jobId,
      chars: trimmed.length,
    });

    begin(job, withUser);
  }

  function startPlan() {
    track("plan_requested");
    router.push("/plan");
  }

  function startAgain() {
    track("start_again");
    clearSession();
    setError(null);
  }

  const pending = chatJob !== null;
  const started = conversation.messages.length > 0;

  return {
    conversation,
    draft,
    setDraft,
    pending,
    error,
    send,
    startPlan,
    startAgain,
    started,
  };
}
