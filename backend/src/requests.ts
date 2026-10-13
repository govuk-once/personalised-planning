export type Kind = "chat" | "plan";

export type Message = {
  role: "user" | "assistant";
  content: string;
};

export type Context = Record<string, unknown> | null;

export type ChatRequest = {
  messages: Message[];
  user_context: Context;
};

export type PlanRequest = {
  situation: string;
  user_context: Context;
  mock: boolean;
};

export type AgentRequest = ChatRequest | PlanRequest;
