import { describe, expect, it } from "vitest";

import { DEFAULT_SETTINGS } from "@/constants/settings";
import {
  clampQuestionCount,
  parseSettings,
} from "@/features/settings/utils/settings";

describe("parseSettings", () => {
  it("returns the defaults for empty input", () => {
    expect(parseSettings(undefined)).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings("nope")).toEqual(DEFAULT_SETTINGS);
  });

  it("keeps valid fields and replaces only the invalid ones", () => {
    expect(
      parseSettings({
        questionCount: 99,
        learningLevel: "advanced",
        theme: "dark",
      }),
    ).toEqual({
      questionCount: DEFAULT_SETTINGS.questionCount,
      learningLevel: "advanced",
      theme: "dark",
    });
  });

  it("ignores fields from older versions", () => {
    expect(
      parseSettings({ ...DEFAULT_SETTINGS, provider: "anthropic" }),
    ).toEqual(DEFAULT_SETTINGS);
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
