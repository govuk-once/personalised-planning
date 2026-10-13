"use client";

import { useEffect, useRef, useState } from "react";

import { usePlanPolling } from "@/hooks/use-plan-polling";
import { usePlanStart } from "@/hooks/use-plan-start";
import { SITE_UPDATED } from "@/lib/action-failure";
import { situationOf } from "@/lib/conversation";
import { onLoad } from "@/lib/plan-page";
import { clearPlanJob, useConversation, useHydrated, usePlan, usePlanJob } from "@/lib/session";

const PLAN_POLLING = {
  intervalMs: 10_000,
  timeoutMs: 600_000,
  missWindowMs: 60_000,
};

function reloadPage() {
  window.location.reload();
}

export function usePlanGeneration() {
  const hydrated = useHydrated();
  const plan = usePlan();
  const planJob = usePlanJob();
  const conversation = useConversation();
  const [error, setError] = useState<string | null>(null);
  const { starting, generate } = usePlanStart(setError);
  const requested = useRef(false);

  const situation = situationOf(conversation);
  const { collectedFacts } = conversation;

  usePlanPolling(planJob, PLAN_POLLING, setError);

  useEffect(() => {
    if (!hydrated || requested.current) {
      return;
    }

    const next = onLoad(plan, planJob, situation);

    if (next === "wait") {
      return;
    }

    requested.current = true;

    if (next === "ask again" && planJob) {
      generate(situation, collectedFacts, planJob);
    }

    if (next === "start") {
      generate(situation, collectedFacts);
    }
  }, [hydrated, plan, planJob, situation, collectedFacts, generate]);

  function retryFor(): (() => void) | null {
    if (error === SITE_UPDATED) {
      return reloadPage;
    }

    if (!situation) {
      return null;
    }

    return () => {
      clearPlanJob();
      generate(situation, collectedFacts);
    };
  }

  const busy = starting || planJob !== null;
  const generating = busy && error === null;
  const retry = retryFor();

  return {
    hydrated,
    plan,
    generating,
    error,
    retry,
  };
}
