import { unstable_isUnrecognizedActionError } from "next/navigation";

export const SITE_UPDATED = "This page has been updated. Reload the page and try again.";

export function failedCall(error: unknown): { ok: false; error: string } {
  return {
    ok: false,
    error: unstable_isUnrecognizedActionError(error)
      ? SITE_UPDATED
      : "Something went wrong. Please try again.",
  };
}
