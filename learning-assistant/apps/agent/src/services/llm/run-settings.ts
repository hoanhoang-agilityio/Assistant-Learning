import { DEFAULT_SETTINGS } from "@repo/shared/constants/settings";
import { SettingsSchema } from "@repo/shared/schemas";

import { MISSING_API_KEY_ERROR } from "../../constants/errors";
import type { RunSettingsResult } from "../../types/llm";

/**
 * Turns `forwardedProps.settings` and the user's saved key into settings that
 * can run. Invalid input falls back to the defaults.
 */
export const resolveRunSettings = (
  raw: unknown,
  apiKey: string | undefined,
): RunSettingsResult => {
  const trimmedKey = apiKey?.trim();
  if (!trimmedKey) {
    return { ok: false, error: MISSING_API_KEY_ERROR };
  }

  const parsed = SettingsSchema.safeParse(raw);
  const settings = parsed.success ? parsed.data : DEFAULT_SETTINGS;

  return { ok: true, settings: { ...settings, apiKey: trimmedKey } };
};
