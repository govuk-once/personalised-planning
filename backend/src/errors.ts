export type ErrorDescription = {
  name: string;
  message: string;
};

const MAX_MESSAGE_LENGTH = 500;

export function describeError(error: unknown): ErrorDescription {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message.slice(0, MAX_MESSAGE_LENGTH),
    };
  }

  const text = String(error);

  return {
    name: typeof error,
    message: text.slice(0, MAX_MESSAGE_LENGTH),
  };
}

export function errorLogFields(error: unknown) {
  const { name, message } = describeError(error);

  return {
    error_type: name,
    error: message,
  };
}

export function isAwsServiceError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }

  return "$metadata" in error;
}

export function hasName(error: unknown, name: string): boolean {
  if (!(error instanceof Error)) {
    return false;
  }

  return error.name === name;
}
