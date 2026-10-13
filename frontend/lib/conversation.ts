import type { StoredConversation } from "@/lib/session";
import type { ChatTurn } from "@/lib/types";

const MAX_SITUATION_LENGTH = 4_000;
const HIGH_SURROGATE = /[\uD800-\uDBFF]/;

export function openerOf(conversation: StoredConversation): string {
  const opener = conversation.messages.find(message => message.role === "user");

  return opener?.content ?? "";
}

function clipped(text: string, length: number): string {
  if (text.length <= length) {
    return text;
  }

  const lastKept = text[length - 1];
  const splitsPair = HIGH_SURROGATE.test(lastKept);
  const end = splitsPair ? length - 1 : length;

  return text.slice(0, end);
}

export function situationOf(conversation: StoredConversation): string {
  const stated = conversation.situation.trim();
  const situation = stated || openerOf(conversation);

  return clipped(situation, MAX_SITUATION_LENGTH);
}

export function withUserMessage(conversation: StoredConversation, text: string) {
  const message = {
    role: "user" as const,
    content: text,
  };

  return {
    ...conversation,
    messages: [...conversation.messages, message],
  };
}

export function withReply(conversation: StoredConversation, turn: ChatTurn) {
  const reply = {
    role: "assistant" as const,
    content: turn.message,
  };

  const stated = turn.situation?.trim();
  const situation = stated || openerOf(conversation);

  return {
    messages: [...conversation.messages, reply],
    lifeEventIds: turn.life_event_ids,
    collectedFacts: turn.collected_facts,
    outstanding: turn.outstanding,
    complete: turn.complete,
    situation,
  };
}

export function unansweredMessage(conversation: StoredConversation): string | null {
  const last = conversation.messages.at(-1);

  if (last?.role !== "user") {
    return null;
  }

  return last.content;
}

export function withoutUnanswered(conversation: StoredConversation) {
  const unanswered = unansweredMessage(conversation);

  if (unanswered === null) {
    return conversation;
  }

  return {
    ...conversation,
    messages: conversation.messages.slice(0, -1),
  };
}
