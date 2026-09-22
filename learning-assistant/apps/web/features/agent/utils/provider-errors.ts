import type { Settings } from "@repo/shared/schemas";

import { PROVIDER_CATALOG } from "@/constants/models";
import {
  ENV_FILE_PATH,
  PROVIDER_ERROR_MATCHERS,
} from "@/features/agent/constants/errors";
import type { ProviderErrorKind } from "@/features/agent/types/errors";

type ProviderSettings = Pick<Settings, "provider" | "model">;

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

/** Which known provider failure this is, or `null` for anything else. */
export const classifyProviderError = (
  error: unknown,
): ProviderErrorKind | null => {
  const statusCode = readStatusCode(error);
  const byStatus = PROVIDER_ERROR_MATCHERS.find(({ statusCodes }) =>
    statusCode === null ? false : statusCodes.includes(statusCode),
  );
  if (byStatus) {
    return byStatus.kind;
  }

  const message = getErrorMessage(error);
  return (
    PROVIDER_ERROR_MATCHERS.find(({ pattern }) => pattern.test(message))
      ?.kind ?? null
  );
};

const describeKind = (
  kind: ProviderErrorKind,
  { provider, model }: ProviderSettings,
): string => {
  const { label, envKey } = PROVIDER_CATALOG[provider];

  switch (kind) {
    case "auth":
      return `${label} rejected the API key. Check ${envKey} in ${ENV_FILE_PATH}, then restart the dev server.`;
    case "rateLimit":
      return `${label} is rate-limiting requests or the key's quota is used up. Wait a minute and try again, or pick another provider in Settings.`;
    case "model":
      return `The model ${model} is not available with this ${label} key. Pick another model in Settings.`;
    case "overloaded":
      return `${label} is having trouble right now. Try again in a moment.`;
    case "network":
      return `The server could not reach ${label}. Check the connection and try again.`;
  }
};

/**
 * A failure the student can act on. Known provider failures (bad key, rate
 * limit, unknown model, outage, network) get a plain explanation; anything
 * else keeps its own message. The raw message is never repeated for a key
 * error, because providers echo part of the key.
 */
export const formatProviderError = (
  error: unknown,
  settings: ProviderSettings,
): string => {
  const kind = classifyProviderError(error);
  return kind ? describeKind(kind, settings) : getErrorMessage(error);
};
