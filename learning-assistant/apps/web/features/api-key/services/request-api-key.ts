import type { Env } from "@repo/shared/types/env";

import {
  API_KEY_HEADER,
  API_KEY_SEAL_SECRET_ENV_KEY,
} from "@/features/api-key/constants/api-key";
import { unsealApiKey } from "@/features/api-key/services/sealed-api-key";

/**
 * The user's OpenAI API key for this request: the sealed key from its header,
 * opened with the server secret. `undefined` when it is missing or invalid.
 */
export const readApiKeyFromRequest = (
  request: Request,
  env: Env = process.env,
): string | undefined => {
  return unsealApiKey(
    request.headers.get(API_KEY_HEADER),
    env[API_KEY_SEAL_SECRET_ENV_KEY],
  );
};
