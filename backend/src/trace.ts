export type Trace = {
  root?: string;
  parent?: string;
  sampled: boolean;
};

export function currentTrace(): Trace {
  const header = process.env._X_AMZN_TRACE_ID ?? "";
  const parts = header.split(";");
  const pairs = parts.map(part => part.split("="));
  const fields: Record<string, string | undefined> = Object.fromEntries(pairs);

  return {
    root: fields.Root,
    parent: fields.Parent,
    sampled: fields.Sampled === "1",
  };
}

export function currentTraceId(): string | undefined {
  const { root } = currentTrace();
  const digits = root?.slice("1-".length);

  return digits?.replace("-", "");
}
