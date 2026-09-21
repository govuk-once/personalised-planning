"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";

import { createPlan } from "@/app/actions";
import { getSessionId, savePlan, useConversation, useHydrated, usePlan } from "@/lib/session";

export function usePlanGeneration() {
  const hydrated = useHydrated();
  const plan = usePlan();
  const conversation = useConversation();
  const [generating, startGenerating] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const requested = useRef(false);

  const situation =
    conversation.situation.trim() ||
    conversation.messages.find((m) => m.role === "user")?.content ||
    "";

  const generate = useCallback((brief: string, userContext: Record<string, unknown>) => {
    startGenerating(async () => {
      setError(null);
      const result = await createPlan({ sessionId: getSessionId(), situation: brief, userContext });

      if (!result.ok) {
        setError(result.error);
        return;
      }
      if (!result.data.plan) {
        setError("The planner did not return a plan. Try starting again.");
        return;
      }
      savePlan(result.data.plan);
    });
  }, []);

  useEffect(() => {
    if (!hydrated || requested.current) return;

    if (plan) {
      requested.current = true;
      return;
    }
    if (situation) {
      requested.current = true;
      generate(situation, conversation.collectedFacts);
    }
  }, [hydrated, plan, situation, conversation.collectedFacts, generate]);

  const retry = situation ? () => generate(situation, conversation.collectedFacts) : null;

  return { hydrated, plan, generating, error, retry };
}
