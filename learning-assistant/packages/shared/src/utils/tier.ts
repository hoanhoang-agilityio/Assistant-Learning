import { LOWEST_TIER, TIER_THRESHOLDS } from "../constants/scoring";
import type { Tier } from "../schemas";

/** Under 50% Novice, under 80% Practitioner, otherwise Master. */
export const getTier = (percent: number): Tier =>
  TIER_THRESHOLDS.find(({ minPercent }) => percent >= minPercent)?.tier ??
  LOWEST_TIER;

/** The next tier up and the percent it needs; `null` at the top tier. */
export const getNextTier = (
  percent: number,
): { tier: Tier; minPercent: number } | null =>
  [...TIER_THRESHOLDS]
    .reverse()
    .find(({ minPercent }) => percent < minPercent) ?? null;
