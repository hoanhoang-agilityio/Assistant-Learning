import { describe, expect, it } from "vitest";

import { DEFAULT_SETTINGS } from "@/constants/settings";
import { resolveRunSettings } from "@/services/llm/run-settings";

const allKeys = {
  OPENAI_API_KEY: "o",
  ANTHROPIC_API_KEY: "a",
  GOOGLE_GENERATIVE_AI_API_KEY: "g",
};

describe("resolveRunSettings", () => {
  it("fails when no provider has a key", () => {
    const result = resolveRunSettings(DEFAULT_SETTINGS, {});
    expect(result.ok).toBe(false);
  });

  it("keeps valid settings", () => {
    const settings = {
      ...DEFAULT_SETTINGS,
      provider: "anthropic",
      model: "claude-haiku-4-5",
      reasoningEffort: "high",
    };
    expect(resolveRunSettings(settings, allKeys)).toEqual({
      ok: true,
      settings,
    });
  });

  it("uses the defaults for invalid input", () => {
    expect(resolveRunSettings({ provider: "nope" }, allKeys)).toEqual({
      ok: true,
      settings: DEFAULT_SETTINGS,
    });
  });

  it("falls back to the provider's default model", () => {
    const result = resolveRunSettings(
      { ...DEFAULT_SETTINGS, provider: "google", model: "gpt-5.4" },
      allKeys,
    );
    expect(result.ok && result.settings.model).toBe("gemini-3.8-flash");
  });

  it("falls back to a provider with a key, and its default model", () => {
    const result = resolveRunSettings(
      { ...DEFAULT_SETTINGS, provider: "openai", model: "gpt-5.4" },
      { GOOGLE_GENERATIVE_AI_API_KEY: "g" },
    );
    expect(result.ok && result.settings).toMatchObject({
      provider: "google",
      model: "gemini-3.8-flash",
    });
  });
});
