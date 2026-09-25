import { API_KEY_ROUTE } from "@repo/shared/constants/routes";

import { OPENAI_ERROR_MATCHERS } from "../constants/errors";
import { OPENAI_MODEL } from "../constants/openai";
import type { OpenAIErrorKind } from "../types/errors";

/** The message of any thrown value. */
export const getErrorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : String(error);

/**
 * The HTTP status of an AI SDK `APICallError`, also when it is wrapped in a
 * `RetryError` (`lastError`).
 */
const readStatusCode = (error: unknown): number | null => {
  if (!error || typeof error !== "object") {
    return null;
  }
  if ("statusCode" in error && typeof error.statusCode === "number") {
    return error.statusCode;
  }
  if ("lastError" in error) {
    return readStatusCode(error.lastError);
  }
  return null;
};

/** Which known OpenAI failure this is, or `null` for anything else. */
export const classifyOpenAIError = (error: unknown): OpenAIErrorKind | null => {
  const statusCode = readStatusCode(error);
  const byStatus = OPENAI_ERROR_MATCHERS.find(({ statusCodes }) =>
    statusCode === null ? false : statusCodes.includes(statusCode),
  );
  if (byStatus) {
    return byStatus.kind;
  }

  const message = getErrorMessage(error);
  return (
    OPENAI_ERROR_MATCHERS.find(({ pattern }) => pattern.test(message))?.kind ??
    null
  );
};

const describeKind = (kind: OpenAIErrorKind): string => {
  switch (kind) {
    case "auth":
      return `OpenAI rejected your API key. Enter a valid key on the API key page (${API_KEY_ROUTE}).`;
    case "rateLimit":
      return "OpenAI is rate-limiting requests or the key's quota is used up. Wait a minute and try again, or check the key's billing.";
    case "model":
      return `The model ${OPENAI_MODEL} is not available with this OpenAI key. Check that the key's project has access to it.`;
    case "overloaded":
      return "OpenAI is having trouble right now. Try again in a moment.";
    case "network":
      return "The server could not reach OpenAI. Check the connection and try again.";
  }
};

/**
 * A failure the student can act on. Known OpenAI failures (bad key, rate
 * limit, unknown model, outage, network) get a plain explanation; anything
 * else keeps its own message. The raw message is never repeated for a key
 * error, because OpenAI echoes part of the key.
 */
export const formatOpenAIError = (error: unknown): string => {
  const kind = classifyOpenAIError(error);
  return kind ? describeKind(kind) : getErrorMessage(error);
};
