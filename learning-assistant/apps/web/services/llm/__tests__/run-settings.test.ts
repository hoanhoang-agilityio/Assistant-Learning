import { describe, expect, it } from "vitest";

import { DEFAULT_SETTINGS } from "@/constants/settings";
import { resolveRunSettings } from "@/services/llm/run-settings";

const API_KEY = "sk-test";

describe("resolveRunSettings", () => {
  it.each([undefined, "", "   "])("fails without an API key (%j)", (apiKey) => {
    expect(resolveRunSettings(DEFAULT_SETTINGS, apiKey).ok).toBe(false);
  });

  it("adds the trimmed API key", () => {
    expect(resolveRunSettings(DEFAULT_SETTINGS, ` ${API_KEY} `)).toEqual({
      ok: true,
      settings: { ...DEFAULT_SETTINGS, apiKey: API_KEY },
    });
  });

  it("keeps valid settings", () => {
    const settings = {
      questionCount: 12,
      learningLevel: "advanced",
      theme: "dark",
    };
    expect(resolveRunSettings(settings, API_KEY)).toEqual({
      ok: true,
      settings: { ...settings, apiKey: API_KEY },
    });
  });

  it("uses the defaults for invalid input", () => {
    expect(resolveRunSettings({ questionCount: 99 }, API_KEY)).toEqual({
      ok: true,
      settings: { ...DEFAULT_SETTINGS, apiKey: API_KEY },
    });
  });
});
