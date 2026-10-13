"use client";

// A reload aborts the requests in flight
const SETTLE_MS = 500;

let leaving = false;

function leave(): void {
  leaving = true;
}

function stay(): void {
  leaving = false;
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", leave);
  window.addEventListener("pagehide", leave);
  window.addEventListener("pageshow", stay);
}

export function undoUnlessLeaving(undo: () => void): void {
  if (leaving) {
    return;
  }

  setTimeout(() => {
    if (!leaving) {
      undo();
    }
  }, SETTLE_MS);
}
