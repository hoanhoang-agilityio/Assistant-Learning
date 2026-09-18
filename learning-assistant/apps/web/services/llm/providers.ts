import { PROVIDERS, type Provider } from "@repo/shared/schemas";

import { PROVIDER_CATALOG } from "../../constants/models";
import type { Env } from "../../types/env";

export const hasProviderKey = (
  provider: Provider,
  env: Env = process.env,
): boolean => {
  return Boolean(env[PROVIDER_CATALOG[provider].envKey]?.trim());
};

/**
 * Providers whose API key is set in the server environment, in catalog order.
 * Server-only: reads `process.env`, and the result is what Settings may show.
 */
export const getAvailableProviders = (env: Env = process.env): Provider[] => {
  return PROVIDERS.filter((provider) => hasProviderKey(provider, env));
};
