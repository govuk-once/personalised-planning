"use client";

import { AwsRum, type AwsRumConfig } from "aws-rum-web";
import { useEffect } from "react";

import { sessionLabel, watch } from "@/lib/monitoring";

// Set by Amplify, but unset locally
const APP_MONITOR_ID = process.env.NEXT_PUBLIC_RUM_APP_MONITOR_ID;

// Build's git commit to link source maps
const RELEASE_ID = process.env.NEXT_PUBLIC_RUM_RELEASE_ID;

const REGION = process.env.NEXT_PUBLIC_RUM_REGION ?? "eu-west-2";

const HTTP_TELEMETRY = {
  addXRayTraceIdHeader: true,
  recordAllRequests: true,
};

let started = false;

function config(): AwsRumConfig {
  const sessionAttributes = sessionLabel();

  return {
    endpoint: `https://dataplane.rum.${REGION}.amazonaws.com`,
    sessionSampleRate: 1,
    allowCookies: true,
    enableXRay: true,
    enableW3CTraceId: true,
    signing: false,
    releaseId: RELEASE_ID,
    sessionAttributes,
    telemetries: ["errors", "performance", ["http", HTTP_TELEMETRY]],
  };
}

function start(): void {
  if (!APP_MONITOR_ID || started) {
    return;
  }

  started = true;

  try {
    const settings = config();
    const rum = new AwsRum(APP_MONITOR_ID, "1.0.0", REGION, settings);

    watch(rum);
  } catch (error) {
    console.warn("CloudWatch RUM didn't start", error);
  }
}

export function UserMonitoring() {
  useEffect(start, []);

  return null;
}
