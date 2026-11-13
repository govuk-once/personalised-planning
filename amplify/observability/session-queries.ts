// The dashboard swaps this for the session id typed into its box.
export const SESSION = "pp-paste-a-session-id";

// The agents' own lines, without their tracing library's copies and spans.
const NOT_COPIES = `filter @logStream not like "otel-rt-logs" and @logStream != "spans" and @message not like "[trace_id="`;

const TURN_STEPS = `["Backend called", "Job started", "Job done", "Job failed"]`;

// One row for each message and for the plan.
export function turnsQuery(): string[] {
  return [
    `filter session_id = "${SESSION}" and message in ${TURN_STEPS}`,
    "stats min(@timestamp) as started, latest(kind) as job, max(ms) as website_ms, max(seconds) as worker_seconds, latest(message) as last_step, latest(reason) as failure by trace_id",
    "sort started asc",
  ];
}

// Pages, the app's own events (pp.*), errors and failed requests.
export function browserQuery(): string[] {
  const shown = `event_type like "page_view" or event_type like "js_error" or event_type like "pp."`;
  const failed =
    "event_details.response.status >= 400 or ispresent(event_details.error.type)";
  const event = `replace(replace(event_type, "com.amazon.rum.", ""), "pp.", "")`;
  const detail =
    "coalesce(event_details.message, event_details.task, event_details.job_id, event_details.request.url)";

  return [
    `filter metadata.appSessionId = "${SESSION}"`,
    `filter ${shown} or (event_type like "http_event" and (${failed}))`,
    `fields @timestamp, ${event} as event, metadata.pageId as page, ${detail} as detail, event_details.response.status as status, user_details.sessionId as rum_session`,
    "sort @timestamp asc",
    "limit 500",
  ];
}

export function dynamoDbQuery(): string[] {
  return [
    `filter session_id = "${SESSION}" and message like "DynamoDB "`,
    "fields @timestamp, message as call, item_key, coalesce(wrote, read) as what, outcome, ms",
    "sort @timestamp asc",
    "limit 500",
  ];
}

// This conversation's warnings and errors, and those of no conversation.
export function problemsQuery(account: string): string[] {
  const noConversation = `not ispresent(session_id) or session_id = "unknown"`;
  // A crash isn't a JSON line: each part prints one its own way.
  const crash = String.raw`@message like "Task timed out" or @message like "Invoke Error" or @message like "Traceback" or @message like /^\w*Error: /`;
  const part = `replace(@log, "${account}:", "") as part`;
  const problem = "coalesce(message, substr(@message, 0, 200)) as problem";

  return [
    `filter @message like "${SESSION}" or ${noConversation}`,
    NOT_COPIES,
    `filter level in ["ERROR", "WARNING"] or ${crash}`,
    `fields @timestamp, ${part}, ${problem}, coalesce(error, reason) as why, shown, trace_id`,
    "sort @timestamp asc",
  ];
}

// Each agent run, each Claude call and each tool call.
export function agentStepsQuery(): string[] {
  const steps = `name = "AgentCore.Runtime.Invoke" or name like "chat " or name like "execute_tool "`;

  return [
    `filter attributes.session.id = "${SESSION}"`,
    `filter ${steps}`,
    "stats count(*) as calls, sum(durationNano) / 1000000000 as seconds, max(durationNano) / 1000000000 as longest, sum(attributes.gen_ai.usage.input_tokens) as tokens_in, sum(attributes.gen_ai.usage.output_tokens) as tokens_out by resource.attributes.service.name as agent, name as step",
    "sort agent, seconds desc",
  ];
}

// Bedrock's own record of each Claude call: open a row for the full prompt.
export function claudeCallsQuery(): string[] {
  return [
    `filter requestMetadata.session_id = "${SESSION}"`,
    "fields @timestamp, operation, modelId as model, input.inputTokenCount as tokens_in, output.outputTokenCount as tokens_out, output.outputBodyJson.stopReason as stopped, requestId as request_id",
    "sort @timestamp asc",
    "limit 500",
  ];
}
