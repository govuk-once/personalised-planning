import { currentTraceId } from "./trace.ts";

export type Level = "INFO" | "WARNING" | "ERROR";

export type Sink = (line: string) => void;

export type Log = (
  level: Level,
  message: string,
  fields?: Record<string, unknown>
) => void;

// Not console.log, which Lambda prefixes: Logs Insights needs a bare JSON line.
export const stdout: Sink = line => {
  process.stdout.write(`${line}\n`);
};

export function logger(sink: Sink, agentName: string, sessionId: string): Log {
  return (level, message, fields = {}) => {
    const timestamp = new Date().toISOString();
    const traceId = currentTraceId();

    const entry = {
      timestamp,
      level,
      agent_name: agentName,
      session_id: sessionId,
      trace_id: traceId,
      message,
      ...fields,
    };

    const line = JSON.stringify(entry);

    sink(line);
  };
}
