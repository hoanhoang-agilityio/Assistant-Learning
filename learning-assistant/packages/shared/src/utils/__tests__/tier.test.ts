import { describe, expect, it } from "vitest";

import { getNextTier, getTier } from "../tier";

describe("getTier", () => {
  it.each([
    [0, "Novice"],
    [49, "Novice"],
    [50, "Practitioner"],
    [79, "Practitioner"],
    [80, "Master"],
    [100, "Master"],
  ])("%i%% is %s", (percent, tier) => {
    expect(getTier(percent)).toBe(tier);
  });
});

describe("getNextTier", () => {
  it.each([
    [0, { tier: "Practitioner", minPercent: 50 }],
    [49, { tier: "Practitioner", minPercent: 50 }],
    [50, { tier: "Master", minPercent: 80 }],
    [79, { tier: "Master", minPercent: 80 }],
  ])("from %i%% is %o", (percent, next) => {
    expect(getNextTier(percent)).toEqual(next);
  });

  it("is null at the top tier", () => {
    expect(getNextTier(80)).toBeNull();
    expect(getNextTier(100)).toBeNull();
  });
});
