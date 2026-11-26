"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { useChatPolling } from "@/hooks/use-chat-polling";
import { useChatStart } from "@/hooks/use-chat-start";
import { useShownError } from "@/hooks/use-shown-error";
import { helpersShown } from "@/lib/answer-helpers";
import { type Answer, sentDetails, TYPED } from "@/lib/answer-tracking";
import { chatJobFor } from "@/lib/chat-job";
import { withUserMessage } from "@/lib/conversation";
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
  const pending = chatJob !== null;
  const helpers = helpersShown(conversation, pending);

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

  function send(text: string, answer: Answer = TYPED) {
    const trimmed = text.trim();

    if (!trimmed || chatJob) {
      return;
    }

    const job = chatJobFor(trimmed, answer);
    const withUser = withUserMessage(conversation, trimmed);
    const sent = sentDetails(job, answer, helpers);

    setError(null);
    setDraft("");
    saveConversation(withUser);
    saveChatJob(job);
    getSessionId();
    track("message_sent", sent);
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
    helpers,
  };
}
