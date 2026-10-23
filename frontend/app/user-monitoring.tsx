"use client";

import { AwsRum, type AwsRumConfig } from "aws-rum-web";
import { useEffect } from "react";

// Set by Amplify, but unset locally
const APP_MONITOR_ID = process.env.NEXT_PUBLIC_RUM_APP_MONITOR_ID;

// Build's git commit to link source maps
const RELEASE_ID = process.env.NEXT_PUBLIC_RUM_RELEASE_ID;

const REGION = process.env.NEXT_PUBLIC_RUM_REGION ?? "eu-west-2";

let started = false;

function config(): AwsRumConfig {
  return {
    endpoint: `https://dataplane.rum.${REGION}.amazonaws.com`,
    sessionSampleRate: 1,
    allowCookies: true,
    enableXRay: true,
    signing: false,
    releaseId: RELEASE_ID,
    telemetries: ["errors", "performance", ["http", { addXRayTraceIdHeader: true }]],
  };
}

function start(): void {
  if (!APP_MONITOR_ID || started) {
    return;
  }

  started = true;

  try {
    const settings = config();

    new AwsRum(APP_MONITOR_ID, "1.0.0", REGION, settings);
  } catch (error) {
    console.warn("CloudWatch RUM didn't start", error);
  }
}

export function UserMonitoring() {
  useEffect(start, []);

  return null;
}
