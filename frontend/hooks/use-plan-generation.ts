"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";

import { createPlanRequest } from "@/app/actions";
import { failedCall } from "@/lib/action-failure";
import { callDirect, describeDirectFailure } from "@/lib/direct-request";
import { getSessionId, savePlan, useConversation, useHydrated, usePlan } from "@/lib/session";
import type { PlanResult } from "@/lib/types";

const TIMEOUT_MS = 300_000;
const TOO_LONG = "The plan took too long and was cancelled. Try again.";

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
      const sessionId = getSessionId();
      const target = await createPlanRequest({ sessionId, situation: brief, userContext }).catch(
        failedCall
      );

      if (!target.ok) {
        setError(target.error);
        return;
      }

      try {
        const result = await callDirect<PlanResult>(target.data, sessionId, TIMEOUT_MS);
        if (!result.plan) {
          setError("The planner did not return a plan. Try starting again.");
          return;
        }
        savePlan(result.plan);
      } catch (caught) {
        setError(describeDirectFailure(caught, TOO_LONG));
      }
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
