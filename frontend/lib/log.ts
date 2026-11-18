import "server-only";

type Level = "INFO" | "WARNING" | "ERROR";

type Fields = Record<string, unknown>;

export function log(level: Level, message: string, fields: Fields): void {
  const entry = {
    level,
    message,
    ...fields,
  };

  const line = JSON.stringify(entry);

  console.log(line);
}
