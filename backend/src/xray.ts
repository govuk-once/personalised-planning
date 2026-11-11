import { randomBytes } from "node:crypto";
import { createSocket, type Socket } from "node:dgram";

import { currentTrace } from "./trace.ts";

export type Subsegment = {
  name: string;
  startMs: number;
  endMs: number;
  aws: Record<string, unknown>;
  statusCode: number;
};

// The X-Ray UDP format
const HEADER = '{"format":"json","version":1}\n';

let socket: Socket | null = null;

function daemonSocket(): Socket {
  if (!socket) {
    socket = createSocket("udp4");
    socket.unref();
  }

  return socket;
}

// If a subsegment can't be sent, drop it
function ignoreFailure(): void {}

export function sendSubsegment(subsegment: Subsegment): void {
  const daemon = process.env.AWS_XRAY_DAEMON_ADDRESS;
  const trace = currentTrace();

  if (!daemon || !trace.root || !trace.parent || !trace.sampled) {
    return;
  }

  const { statusCode } = subsegment;
  const id = randomBytes(8).toString("hex");

  const document = {
    name: subsegment.name,
    id,
    trace_id: trace.root,
    parent_id: trace.parent,
    start_time: subsegment.startMs / 1000,
    end_time: subsegment.endMs / 1000,
    type: "subsegment",
    namespace: "aws",
    aws: subsegment.aws,
    http: { response: { status: statusCode } },
    error: statusCode >= 400 && statusCode < 500,
    fault: statusCode >= 500,
  };

  const message = HEADER + JSON.stringify(document);
  const [host, port] = daemon.split(":");
  const portNumber = Number(port);

  daemonSocket().send(message, portNumber, host, ignoreFailure);
}
