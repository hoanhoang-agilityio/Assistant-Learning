"use server";

import {
  API_KEY_ERRORS,
  API_KEY_FIELD,
  API_KEY_SEAL_SECRET_ENV_KEY,
} from "@/features/api-key/constants/api-key";
import { sealApiKey } from "@/features/api-key/services/sealed-api-key";
import { validateApiKey } from "@/features/api-key/services/validate-api-key";
import type { ApiKeySubmitResult } from "@/features/api-key/types/api-key";
import { normalizeApiKey } from "@/features/api-key/utils/api-key";

/**
 * Checks the submitted key with OpenAI and returns it sealed, so the browser
 * can keep it without ever storing the plain key.
 */
export const submitApiKey = async (
  formData: FormData,
): Promise<ApiKeySubmitResult> => {
  const secret = process.env[API_KEY_SEAL_SECRET_ENV_KEY];
  if (!secret) {
    return { ok: false, error: API_KEY_ERRORS.missingSecret };
  }

  const apiKey = normalizeApiKey(formData.get(API_KEY_FIELD));
  const result = await validateApiKey(apiKey);
  if (!result.ok) {
    return result;
  }

  return { ok: true, sealedKey: sealApiKey(apiKey, secret) };
};
