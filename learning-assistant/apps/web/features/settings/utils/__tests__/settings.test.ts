import type { Settings } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { DEFAULT_SETTINGS } from "@/constants/settings";
import {
  clampQuestionCount,
  parseSettings,
  reconcileProvider,
  selectModel,
  selectProvider,
} from "@/features/settings/utils/settings";

const anthropic: Settings = {
  ...DEFAULT_SETTINGS,
  provider: "anthropic",
  model: "claude-sonnet-5",
  reasoningEffort: "high",
};

describe("parseSettings", () => {
  it("returns the defaults for empty input", () => {
    expect(parseSettings(undefined)).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings("nope")).toEqual(DEFAULT_SETTINGS);
  });

  it("keeps valid fields and replaces only the invalid ones", () => {
    expect(
      parseSettings({ ...anthropic, questionCount: 99, theme: "dark" }),
    ).toEqual({
      ...anthropic,
      questionCount: DEFAULT_SETTINGS.questionCount,
      theme: "dark",
    });
  });

  it("falls back to the provider's default model off the allowlist", () => {
    expect(parseSettings({ ...anthropic, model: "gpt-5.4" }).model).toBe(
      "claude-sonnet-5",
    );
  });
});

describe("selectProvider", () => {
  it("moves to the provider's default model", () => {
    expect(selectProvider(DEFAULT_SETTINGS, "google")).toMatchObject({
      provider: "google",
      model: "gemini-3.8-flash",
    });
  });

  it("returns the same object when the provider is unchanged", () => {
    expect(selectProvider(anthropic, "anthropic")).toBe(anthropic);
  });
});

describe("selectModel", () => {
  it("switches to an allowed model", () => {
    expect(selectModel(anthropic, "claude-haiku-4-5").model).toBe(
      "claude-haiku-4-5",
    );
  });

  it("ignores a model from another provider", () => {
    expect(selectModel(anthropic, "gpt-5.4")).toBe(anthropic);
  });
});

describe("clampQuestionCount", () => {
  it.each([
    [1, 3],
    [7.4, 7],
    [50, 20],
    [Number.NaN, 5],
  ])("clamps %s to %s", (input, expected) => {
    expect(clampQuestionCount(input)).toBe(expected);
  });
});

describe("reconcileProvider", () => {
  it("keeps a provider that has a key", () => {
    expect(reconcileProvider(anthropic, ["openai", "anthropic"])).toBe(
      anthropic,
    );
  });

  it("moves to the first provider with a key", () => {
    expect(reconcileProvider(anthropic, ["google"])).toMatchObject({
      provider: "google",
      model: "gemini-3.8-flash",
    });
  });

  it("keeps the settings when no provider has a key", () => {
    expect(reconcileProvider(anthropic, [])).toBe(anthropic);
  });
});
