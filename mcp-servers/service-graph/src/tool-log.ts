type Fields = Record<string, unknown>;

function traceId(): string | undefined {
  const header = process.env._X_AMZN_TRACE_ID ?? '';
  const parts = header.split(';');
  const root = parts.find(part => part.startsWith('Root=1-'));
  const digits = root?.slice('Root=1-'.length);

  return digits?.replace('-', '');
}

export function log(level: string, message: string, fields: Fields): void {
  const entry = {
    level,
    message,
    trace_id: traceId(),
    ...fields,
  };

  const line = JSON.stringify(entry);

  process.stdout.write(`${line}\n`);
}
