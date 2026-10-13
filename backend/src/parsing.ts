export type Valid<T> = {
  ok: true;
  value: T;
};

export type Invalid = {
  ok: false;
  problems: string[];
};

export type Parsed<T> = Valid<T> | Invalid;

export function parsed<T>(
  checks: Record<string, boolean>,
  build: () => T
): Parsed<T> {
  const fields = Object.keys(checks);
  const problems = fields.filter(field => !checks[field]);

  if (problems.length > 0) {
    return {
      ok: false,
      problems,
    };
  }

  const value = build();

  return {
    ok: true,
    value,
  };
}
