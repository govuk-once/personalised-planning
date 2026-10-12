"use client";

import * as storage from "@/lib/storage";
import type { ChatMessage, Plan } from "@/lib/types";

export const KEYS = ["sessionId", "conversation", "plan", "chatJob", "planJob"] as const;
const [SESSION_ID, CONVERSATION, PLAN, CHAT_JOB, PLAN_JOB] = KEYS;

export type StoredJob = {
  jobId: string;
  startedAt: number;
  // Only false means unconfirmed: a reload then asks the backend for the job again.
  confirmed?: boolean;
};

export type StoredChatJob = StoredJob & { text: string };

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

export const useChatJob = () => storage.useStored<StoredChatJob | null>(CHAT_JOB, null);
export const usePlanJob = () => storage.useStored<StoredJob | null>(PLAN_JOB, null);

export const saveConversation = (value: StoredConversation) => storage.write(CONVERSATION, value);
export const savePlan = (value: Plan) => storage.write(PLAN, value);
export const saveChatJob = (value: StoredChatJob) => storage.write(CHAT_JOB, value);
export const savePlanJob = (value: StoredJob) => storage.write(PLAN_JOB, value);
export const clearChatJob = () => storage.remove(CHAT_JOB);
export const clearPlanJob = () => storage.remove(PLAN_JOB);

export const clearSession = () => storage.removeAll(KEYS);

export { useHydrated } from "@/lib/storage";
