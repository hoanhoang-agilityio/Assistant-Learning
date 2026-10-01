import { describe, expect, it } from "vitest";

import { ProfileUpdateSchema } from "../../schemas";
import {
  calculateConceptPercent,
  countConceptResults,
  toConceptKey,
} from "../memory";

describe("toConceptKey", () => {
  it("ignores case and spacing", () => {
    expect(toConceptKey("  Lexical   Scope ")).toBe("lexical scope");
  });
});

describe("calculateConceptPercent", () => {
  it("rounds to a whole percent", () => {
    expect(calculateConceptPercent(2, 3)).toBe(67);
  });

  it("is 0 without questions", () => {
    expect(calculateConceptPercent(0, 0)).toBe(0);
  });
});

describe("countConceptResults", () => {
  it("counts questions per concept and the right ones from the mastery", () => {
    const questions = [
      { concept: "Closures" },
      { concept: "closures" },
      { concept: "Scope" },
    ];
    const mastery = [
      { concept: "Closures", percent: 50 },
      { concept: "Scope", percent: 100 },
    ];

    expect(countConceptResults(questions, mastery)).toEqual([
      { key: "closures", concept: "Closures", correct: 1, total: 2 },
      { key: "scope", concept: "Scope", correct: 1, total: 1 },
    ]);
  });

  it("counts a concept missing from the mastery as all wrong", () => {
    expect(countConceptResults([{ concept: "Scope" }], [])).toEqual([
      { key: "scope", concept: "Scope", correct: 0, total: 1 },
    ]);
  });
});

describe("ProfileUpdateSchema", () => {
  it("takes a field to forget as null", () => {
    expect(ProfileUpdateSchema.parse({ style: null })).toEqual({
      style: null,
    });
  });

  it("needs at least one field", () => {
    expect(ProfileUpdateSchema.safeParse({}).success).toBe(false);
  });

  it("refuses a level that is not one of the settings' levels", () => {
    expect(ProfileUpdateSchema.safeParse({ level: "expert" }).success).toBe(
      false,
    );
  });
});
