"use client";

import * as storage from "@/lib/storage";
import type { ChatMessage, Plan } from "@/lib/types";

export const KEYS = ["sessionId", "conversation", "plan"] as const;
const [SESSION_ID, CONVERSATION, PLAN] = KEYS;

export type StoredConversation = {
  messages: ChatMessage[];
  lifeEventIds: string[];
  collectedFacts: Record<string, unknown>;
  outstanding: string[];
  complete: boolean;
  situation: string;
};

export const emptyConversation: StoredConversation = {
  messages: [],
  lifeEventIds: [],
  collectedFacts: {},
  outstanding: [],
  complete: false,
  situation: "",
};

/** AgentCore rejects session ids shorter than 33 characters; a UUID is 36. */
export function getSessionId(): string {
  const existing = storage.read<string | null>(SESSION_ID, null);
  if (existing) return existing;

  const created = `pp-${crypto.randomUUID()}`;
  storage.write(SESSION_ID, created);
  return created;
}

export const useConversation = () => storage.useStored(CONVERSATION, emptyConversation);
export const usePlan = () => storage.useStored<Plan | null>(PLAN, null);

export const saveConversation = (value: StoredConversation) => storage.write(CONVERSATION, value);
export const savePlan = (value: Plan) => storage.write(PLAN, value);

export const clearSession = () => storage.removeAll(KEYS);

export { useHydrated } from "@/lib/storage";
