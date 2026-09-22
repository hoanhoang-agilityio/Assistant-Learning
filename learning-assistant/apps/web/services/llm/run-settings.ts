import { PROVIDERS, SettingsSchema } from "@repo/shared/schemas";

import { PROVIDER_CATALOG } from "@/constants/models";
import { DEFAULT_SETTINGS } from "@/constants/settings";
import { getAvailableProviders } from "@/services/llm/providers";
import type { Env } from "@/types/env";
import type { RunSettingsResult } from "@/types/llm";
import {
  getDefaultModel,
  isAllowedModel,
  supportsReasoning,
} from "@/utils/models";

const missingKeysError = `No LLM provider is configured. Set one of ${PROVIDERS.map(
  (provider) => PROVIDER_CATALOG[provider].envKey,
).join(", ")}.`;

/**
 * Turns `forwardedProps.settings` into settings that can run. Invalid input
 * falls back to the defaults, a provider without a key falls back to the first
 * provider with one, and a model off the allowlist falls back to the
 * provider's default model.
 */
export const resolveRunSettings = (
  raw: unknown,
  env: Env = process.env,
): RunSettingsResult => {
  const parsed = SettingsSchema.safeParse(raw);
  const requested = parsed.success ? parsed.data : DEFAULT_SETTINGS;

  const available = getAvailableProviders(env);
  const [firstAvailable] = available;
  if (!firstAvailable) {
    return { ok: false, error: missingKeysError };
  }

  const provider = available.includes(requested.provider)
    ? requested.provider
    : firstAvailable;
  const model =
    provider === requested.provider && isAllowedModel(provider, requested.model)
      ? requested.model
      : getDefaultModel(provider).id;
  const reasoningEffort = supportsReasoning(provider, model)
    ? requested.reasoningEffort
    : "off";

  return {
    ok: true,
    settings: { ...requested, provider, model, reasoningEffort },
  };
};
