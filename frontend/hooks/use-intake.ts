"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { useChatPolling } from "@/hooks/use-chat-polling";
import { useChatStart } from "@/hooks/use-chat-start";
import { withUserMessage } from "@/lib/conversation";
import { freshJob } from "@/lib/job-id";
import {
  clearSession,
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
  const [error, setError] = useState<string | null>(null);

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
    begin(job, withUser);
  }

  function startPlan() {
    router.push("/plan");
  }

  function startAgain() {
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
