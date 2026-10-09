import {
  CONNECTION_EXCEPTION_CLASS,
  MAX_ERROR_CAUSE_DEPTH,
  UNAVAILABLE_ERROR_MESSAGES,
  UNAVAILABLE_SQLSTATES,
  UNREACHABLE_ERROR_CODES,
} from "./constants";

const isUnavailableCode = (code: unknown): boolean =>
  typeof code === "string" &&
  (UNREACHABLE_ERROR_CODES.includes(code) ||
    UNAVAILABLE_SQLSTATES.includes(code) ||
    code.startsWith(CONNECTION_EXCEPTION_CLASS));

/**
 * Whether `error` means the database cannot serve requests right now (not
 * configured, unreachable, not migrated) rather than that a query was
 * wrong. Follows `cause`, since Drizzle wraps the driver's error.
 */
export const isDatabaseUnavailableError = (
  error: unknown,
  depth = 0,
): boolean => {
  if (!(error instanceof Error) || depth > MAX_ERROR_CAUSE_DEPTH) {
    return false;
  }

  const { code } = error as Error & { code?: unknown };
  if (
    isUnavailableCode(code) ||
    UNAVAILABLE_ERROR_MESSAGES.includes(error.message)
  ) {
    return true;
  }
  return isDatabaseUnavailableError(error.cause, depth + 1);
};
