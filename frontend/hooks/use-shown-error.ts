"use client";

import { useCallback, useState } from "react";

import { track } from "@/lib/monitoring";

type Page = "chat" | "plan";

export function useShownError(page: Page) {
  const [error, setShownError] = useState<string | null>(null);

  const setError = useCallback(
    (message: string | null) => {
      setShownError(message);

      if (message) {
        track("error_shown", {
          page,
          message,
        });
      }
    },
    [page]
  );

  return [error, setError] as const;
}
