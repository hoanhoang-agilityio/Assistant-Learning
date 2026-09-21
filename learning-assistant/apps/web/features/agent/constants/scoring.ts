import type { Tier } from "@repo/shared/schemas";

/** Lowest percent for each tier, highest first. Below every bound: Novice. */
export const TIER_THRESHOLDS: readonly { tier: Tier; minPercent: number }[] = [
  { tier: "Master", minPercent: 80 },
  { tier: "Practitioner", minPercent: 50 },
];

export const LOWEST_TIER: Tier = "Novice";
