import { createHmac } from "node:crypto";

const TTL_SECONDS = 600;

export function planTicket(sessionId: string): string {
  const secret = process.env.BACKEND_API_KEY;
  if (!secret) return "";

  const expiry = Math.floor(Date.now() / 1000) + TTL_SECONDS;
  const digest = createHmac("sha256", secret).update(`${sessionId}.${expiry}`).digest("hex");

  return `${expiry}.${digest}`;
}
