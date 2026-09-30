import type { Settings } from "@repo/shared/schemas";

/**
 * Settings for one run, plus the user's OpenAI API key.
 * Server only: never put it in agent state or in a message.
 */
export type RunSettings = Settings & { apiKey: string };

/** A value still being written: any field may be missing, at any depth. */
export type DeepPartial<T> = T extends readonly (infer Item)[]
  ? DeepPartial<Item>[]
  : T extends object
    ? { [Key in keyof T]?: DeepPartial<T[Key]> }
    : T;

/** Settings for one run after checking the key. */
export type RunSettingsResult =
  { ok: true; settings: RunSettings } | { ok: false; error: string };
