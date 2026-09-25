export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ChatTurn = {
  message: string;
  life_event_ids: string[];
  collected_facts: Record<string, unknown>;
  outstanding: string[];
  complete: boolean;
  situation: string | null;
};

export type Task = {
  title: string;
  summary: string;
  callout?: string | null;
  methods: string[];
  dept: string;
  completed: boolean;
  location?: string | null;
  deadline?: string | null;
  grant?: string | null;
  gov_service_name: string;
  gov_service_url: string;
  cost: number;
  service_form_url?: string | null;
  service_form_label?: string | null;
  what_to_expect: string;
  requirements: string[];
};

/** Mirrors StepProgress in agent/app/structured_outputs.py. */
export type StepStatus = "Not started" | "In progress" | "Done";

export type Step = {
  title: string;
  summary: string;
  status: StepStatus;
  tasks: Task[];
};

export type Plan = {
  title: string;
  summary: string;
  steps: Step[];
  reasoning?: string;
};

export type PlanResult = {
  plan: Plan | null;
  agent_help?: { answer: string } | null;
};

export type ActionResult<T> = { ok: true; data: T } | { ok: false; error: string };

export type PlanRequest = {
  url: string;
  ticket: string;
  body: Record<string, unknown> | null;
};
