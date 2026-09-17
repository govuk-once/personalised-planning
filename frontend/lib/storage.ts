"use client";

import { useSyncExternalStore } from "react";

const listeners = new Set<() => void>();
const snapshots = new Map<string, { raw: string | null; value: unknown }>();

const notify = () => listeners.forEach(listener => listener());

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function snapshot<T>(key: string, fallback: T): T {
  const raw = typeof window === "undefined" ? null : sessionStorage.getItem(key);
  const cached = snapshots.get(key);
  if (cached && cached.raw === raw) return cached.value as T;

  let value = fallback;
  if (raw) {
    try {
      value = JSON.parse(raw) as T;
    } catch {
      value = fallback;
    }
  }

  snapshots.set(key, { raw, value });
  return value;
}

export function read<T>(key: string, fallback: T): T {
  return snapshot(key, fallback);
}

export function write(key: string, value: unknown) {
  sessionStorage.setItem(key, JSON.stringify(value));
  notify();
}

export function remove(key: string) {
  sessionStorage.removeItem(key);
  snapshots.delete(key);
  notify();
}

export function removeAll(keys: readonly string[]) {
  keys.forEach(key => sessionStorage.removeItem(key));
  snapshots.clear();
  notify();
}

export const useStored = <T>(key: string, fallback: T): T =>
  useSyncExternalStore(
    subscribe,
    () => snapshot(key, fallback),
    () => fallback
  );

/** True once the browser has taken over from the server-rendered markup. */
export const useHydrated = () =>
  useSyncExternalStore(
    subscribe,
    () => true,
    () => false
  );

export const present = (keys: readonly string[]) =>
  typeof window === "undefined" ? [] : keys.filter(key => sessionStorage.getItem(key) !== null);
