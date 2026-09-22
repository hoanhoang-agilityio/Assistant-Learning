import {
  API_KEY_ERRORS,
  API_KEY_PREFIX,
} from "@/features/api-key/constants/api-key";
import type { ApiKeyCheck } from "@/features/api-key/types/api-key";

/** The submitted form value as a trimmed string; anything else is `""`. */
export const normalizeApiKey = (raw: unknown): string => {
  return typeof raw === "string" ? raw.trim() : "";
};

/** Catches empty and obviously wrong input before calling OpenAI. */
export const checkApiKeyFormat = (apiKey: string): ApiKeyCheck => {
  if (!apiKey) {
    return { ok: false, error: API_KEY_ERRORS.empty };
  }
  if (!apiKey.startsWith(API_KEY_PREFIX) || /\s/.test(apiKey)) {
    return { ok: false, error: API_KEY_ERRORS.format };
  }
  return { ok: true };
};

/** Turns the HTTP status of the OpenAI check into a result. */
export const describeApiKeyStatus = (status: number): ApiKeyCheck => {
  if (status >= 200 && status < 300) {
    return { ok: true };
  }
  switch (status) {
    case 401:
      return { ok: false, error: API_KEY_ERRORS.invalid };
    case 403:
      return { ok: false, error: API_KEY_ERRORS.forbidden };
    case 429:
      return { ok: false, error: API_KEY_ERRORS.rateLimit };
    default:
      return { ok: false, error: API_KEY_ERRORS.unexpected };
  }
};
