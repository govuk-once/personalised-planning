"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";

import { createPlanRequest } from "@/app/actions";
import { failedCall } from "@/lib/action-failure";
import { getSessionId, savePlan, useConversation, useHydrated, usePlan } from "@/lib/session";
import type { PlanRequest, PlanResult } from "@/lib/types";

const TIMEOUT_MS = 300_000;

async function fetchPlan(target: PlanRequest, sessionId: string): Promise<PlanResult> {
  const response = await fetch(target.url, {
    method: target.body ? "POST" : "GET",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Id": sessionId,
      ...(target.ticket ? { "X-Plan-Ticket": target.ticket } : {}),
    },
    body: target.body ? JSON.stringify(target.body) : undefined,
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });

  if (!response.ok) {
    const detail = detailFrom(await response.text());
    throw new Error(detail ?? `The planning service responded with an error (${response.status}).`);
  }

  return (await response.json()) as PlanResult;
}

function detailFrom(body: string): string | null {
  try {
    return (JSON.parse(body) as { detail?: string }).detail ?? null;
  } catch {
    return null;
  }
}

function describe(error: unknown): string {
  if (error instanceof Error && error.name === "TimeoutError") {
    return "The plan took too long and was cancelled. Try again.";
  }
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong. Please try again.";
}

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
        const result = await fetchPlan(target.data, sessionId);
        if (!result.plan) {
          setError("The planner did not return a plan. Try starting again.");
          return;
        }
        savePlan(result.plan);
      } catch (caught) {
        setError(describe(caught));
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
