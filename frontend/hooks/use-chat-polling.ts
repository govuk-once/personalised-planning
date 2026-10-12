"use client";

import { useJobPolling } from "@/hooks/use-job-polling";
import { withReply } from "@/lib/conversation";
import type { Outcome, PollSettings } from "@/lib/poll";
import {
  clearChatJob,
  saveConversation,
  type StoredChatJob,
  type StoredConversation,
} from "@/lib/session";
import type { ChatTurn } from "@/lib/types";

type Handlers = {
  abandon: (job: StoredChatJob, message: string, current: StoredConversation) => void;
  setError: (error: string | null) => void;
};

export function useChatPolling(
  chatJob: StoredChatJob | null,
  conversation: StoredConversation,
  settings: PollSettings,
  handlers: Handlers
) {
  function settle(outcome: Outcome<ChatTurn>) {
    if (outcome.ok) {
      const answered = withReply(conversation, outcome.result);

      saveConversation(answered);
      clearChatJob();
      return;
    }

    if (outcome.keepJob) {
      handlers.setError(outcome.error);
      return;
    }

    if (chatJob) {
      handlers.abandon(chatJob, outcome.error, conversation);
    }
  }

  const confirmedJob = chatJob?.confirmed === false ? null : chatJob;

  useJobPolling<ChatTurn>(confirmedJob, settings, settle);
}
