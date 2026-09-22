import type { Tier } from "../schemas";

/** The Master bound: a concept at or above it counts as mastered. */
export const MASTERED_PERCENT = 80;

/** Lowest percent for each tier, highest first. Below every bound: Novice. */
export const TIER_THRESHOLDS: readonly { tier: Tier; minPercent: number }[] = [
  { tier: "Master", minPercent: MASTERED_PERCENT },
  { tier: "Practitioner", minPercent: 50 },
];

export const LOWEST_TIER: Tier = "Novice";
