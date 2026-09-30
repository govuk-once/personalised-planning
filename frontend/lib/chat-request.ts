import type { ChatInput } from "@/lib/action-input";

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
