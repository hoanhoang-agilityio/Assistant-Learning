import {
  API_KEY_CHECK_TIMEOUT_MS,
  API_KEY_ERRORS,
  OPENAI_MODELS_URL,
} from "@/features/api-key/constants/api-key";
import type { ApiKeyCheck } from "@/features/api-key/types/api-key";
import {
  checkApiKeyFormat,
  describeApiKeyStatus,
} from "@/features/api-key/utils/api-key";

/**
 * Checks the key's format, then asks OpenAI whether it accepts it (listing
 * models is free). Never throws, and never repeats OpenAI's message, which
 * echoes part of the key.
 */
export const validateApiKey = async (apiKey: string): Promise<ApiKeyCheck> => {
  const format = checkApiKeyFormat(apiKey);
  if (!format.ok) {
    return format;
  }

  try {
    const response = await fetch(OPENAI_MODELS_URL, {
      headers: { Authorization: `Bearer ${apiKey}` },
      cache: "no-store",
      signal: AbortSignal.timeout(API_KEY_CHECK_TIMEOUT_MS),
    });
    return describeApiKeyStatus(response.status);
  } catch {
    return { ok: false, error: API_KEY_ERRORS.unreachable };
  }
};
