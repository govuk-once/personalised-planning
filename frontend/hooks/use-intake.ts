"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { sendChatTurn } from "@/app/actions";
import {
  clearSession,
  getSessionId,
  saveConversation,
  useConversation,
  type StoredConversation,
} from "@/lib/session";

export function useIntake() {
  const router = useRouter();
  const conversation = useConversation();
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || pending) return;

    setError(null);
    setDraft("");

    const sessionId = getSessionId();
    const withUser: StoredConversation = {
      ...conversation,
      messages: [...conversation.messages, { role: "user", content: trimmed }],
    };
    saveConversation(withUser);
    setPending(true);

    const result = await sendChatTurn({
      sessionId,
      messages: withUser.messages,
      collectedFacts: conversation.collectedFacts,
    });
    setPending(false);

    // Restore the transcript and draft, or a retry replays two user messages
    const abandon = (message: string) => {
      saveConversation(conversation);
      setDraft(trimmed);
      setError(message);
    };

    if (!result.ok) return abandon(result.error);

    const turn = result.data;
    if (!turn.message.trim()) return abandon("The adviser did not reply. Please try again.");

    const opener = withUser.messages.find(m => m.role === "user")?.content ?? "";
    saveConversation({
      messages: [...withUser.messages, { role: "assistant", content: turn.message }],
      lifeEventIds: turn.life_event_ids,
      collectedFacts: turn.collected_facts,
      outstanding: turn.outstanding,
      complete: turn.complete,
      situation: turn.situation?.trim() || opener,
    });
  }

  return {
    conversation,
    draft,
    setDraft,
    pending,
    error,
    send,
    startPlan: () => router.push("/plan"),
    startAgain: () => {
      clearSession();
      setError(null);
    },
    busy: pending,
    started: conversation.messages.length > 0,
  };
}
