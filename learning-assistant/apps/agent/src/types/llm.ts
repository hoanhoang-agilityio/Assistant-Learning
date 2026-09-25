import type { Settings } from "@repo/shared/schemas";

/**
 * Settings for one run, plus the user's OpenAI API key.
 * Server only: never put it in agent state or in a message.
 */
export type RunSettings = Settings & { apiKey: string };

/** Settings for one run after checking the key. */
export type RunSettingsResult =
  { ok: true; settings: RunSettings } | { ok: false; error: string };
