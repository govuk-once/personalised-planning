import type { ChatInput } from "@/lib/action-input";
import type { StoredConversation } from "@/lib/session";

export function chatBody({ messages, collectedFacts, lifeEventIds, outstanding }: ChatInput) {
  const userContext = {
    ...(collectedFacts ?? {}),
    ...(lifeEventIds?.length ? { life_event_ids: lifeEventIds } : {}),
    ...(outstanding?.length ? { outstanding } : {}),
  };
  return {
    messages,
    user_context: Object.keys(userContext).length > 0 ? userContext : null,
  };
}

export function chatTurnRequest(
  conversation: StoredConversation,
  sessionId: string,
  jobId: string
): ChatInput {
  return {
    sessionId,
    jobId,
    messages: conversation.messages,
    collectedFacts: conversation.collectedFacts,
    lifeEventIds: conversation.lifeEventIds,
    outstanding: conversation.outstanding,
  };
}
