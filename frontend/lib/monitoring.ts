"use client";

import type { AwsRum } from "aws-rum-web";

import { currentSessionId } from "@/lib/session";

type Details = Record<string, string | number | boolean>;

let rum: AwsRum | null = null;

export function sessionLabel(): Record<string, string> {
  const appSessionId = currentSessionId();

  return appSessionId ? { appSessionId } : {};
}

export function watch(instance: AwsRum): void {
  rum = instance;
  instance.setEventMetadataHook(sessionLabel);
}

export function track(event: string, details: Details = {}): void {
  try {
    rum?.recordEvent(`pp.${event}`, details);
  } catch (error) {
    console.warn("CloudWatch RUM didn't record", event, error);
  }
}
