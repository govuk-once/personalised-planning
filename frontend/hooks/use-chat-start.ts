"use client";

import { useEffect, useEffectEvent, useRef, useTransition } from "react";

import { startChatTurn } from "@/app/actions";
import { SITE_UPDATED, startTwice } from "@/lib/action-failure";
import { chatTurnRequest } from "@/lib/chat-request";
import { withoutUnanswered } from "@/lib/conversation";
import { NOT_STARTED, stillStartable } from "@/lib/job-id";
import { undoUnlessLeaving } from "@/lib/page-lifecycle";
import {
  clearChatJob,
  getSessionId,
  saveChatJob,
  saveConversation,
  type StoredChatJob,
  type StoredConversation,
} from "@/lib/session";

type Feedback = {
  setDraft: (draft: string) => void;
  setError: (error: string | null) => void;
};

export function useChatStart(
  conversation: StoredConversation,
  chatJob: StoredChatJob | null,
  feedback: Feedback
) {
  const [, startTransition] = useTransition();
  const asked = useRef<string | null>(null);

  function abandon(job: StoredChatJob, message: string, current: StoredConversation) {
    const restored = withoutUnanswered(current);

    saveConversation(restored);
    clearChatJob();
    feedback.setDraft(job.text);
    feedback.setError(message);
  }

  async function ask(job: StoredChatJob, withUser: StoredConversation) {
    asked.current = job.jobId;

    if (!stillStartable(job)) {
      abandon(job, NOT_STARTED, withUser);
      return;
    }

    const sessionId = getSessionId();
    const request = chatTurnRequest(withUser, sessionId, job.jobId);
    const started = await startTwice(() => startChatTurn(request));

    if (started.ok) {
      const confirmed = {
        ...job,
        confirmed: true,
      };

      saveChatJob(confirmed);
      return;
    }

    if (started.error === SITE_UPDATED) {
      // A reload asks for this job again.
      feedback.setError(started.error);
      return;
    }

    undoUnlessLeaving(() => abandon(job, started.error, withUser));
  }

  function begin(job: StoredChatJob, withUser: StoredConversation) {
    startTransition(() => ask(job, withUser));
  }

  const askAgainAfterReload = useEffectEvent((job: StoredChatJob) => {
    begin(job, conversation);
  });

  useEffect(() => {
    const unconfirmed = chatJob?.confirmed === false;

    if (unconfirmed && asked.current !== chatJob.jobId) {
      askAgainAfterReload(chatJob);
    }
  }, [chatJob]);

  return {
    begin,
    abandon,
  };
}
