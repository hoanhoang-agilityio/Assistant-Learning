import { PROVIDERS, SettingsSchema } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { PROVIDER_CATALOG } from "../../constants/models";
import { DEFAULT_SETTINGS } from "../../constants/settings";
import {
  findModel,
  getDefaultModel,
  isAllowedModel,
  supportsReasoning,
} from "../models";

describe("model catalog", () => {
  it("has at least one model per provider", () => {
    for (const provider of PROVIDERS) {
      expect(PROVIDER_CATALOG[provider].models.length).toBeGreaterThan(0);
    }
  });

  it("uses the first model as the default", () => {
    expect(getDefaultModel("openai").id).toBe("gpt-5.4-mini");
  });

  it("checks models against the provider's allowlist", () => {
    expect(isAllowedModel("anthropic", "claude-sonnet-5")).toBe(true);
    expect(isAllowedModel("anthropic", "gpt-5.4")).toBe(false);
    expect(findModel("google", "gemini-2.5-flash")?.reasoning).toBe(
      "gemini-budget",
    );
    expect(supportsReasoning("google", "unknown")).toBe(false);
  });

  it("has valid default settings", () => {
    expect(SettingsSchema.parse(DEFAULT_SETTINGS)).toEqual(DEFAULT_SETTINGS);
    expect(
      isAllowedModel(DEFAULT_SETTINGS.provider, DEFAULT_SETTINGS.model),
    ).toBe(true);
  });
});
