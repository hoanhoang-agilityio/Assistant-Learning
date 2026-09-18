import type { ReasoningEffort } from "@repo/shared/schemas";

type Enabled = Exclude<ReasoningEffort, "off">;

/** Anthropic `thinking.budgetTokens` for models without adaptive thinking. */
export const ANTHROPIC_THINKING_BUDGET: Record<Enabled, number> = {
  low: 2048,
  medium: 8192,
  high: 16384,
};

/**
 * Gemini 2.5 `thinkingConfig.thinkingBudget`. `0` turns thinking off;
 * 24576 is the 2.5 Flash maximum.
 */
export const GEMINI_THINKING_BUDGET: Record<ReasoningEffort, number> = {
  off: 0,
  low: 1024,
  medium: 8192,
  high: 24576,
};

/**
 * Gemini 3.x `thinkingConfig.thinkingLevel`. Thinking cannot be turned off on
 * 3.x, so `off` maps to the lowest level.
 */
export const GEMINI_THINKING_LEVEL = {
  off: "minimal",
  low: "low",
  medium: "medium",
  high: "high",
} as const satisfies Record<ReasoningEffort, string>;
