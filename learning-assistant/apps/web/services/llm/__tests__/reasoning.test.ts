import { describe, expect, it } from "vitest";

import type { ReasoningKind } from "../../../types/llm";
import { getReasoningOptions, toReasoningOptions } from "../reasoning";

describe("toReasoningOptions", () => {
  it.each<[ReasoningKind, string, object]>([
    ["openai-effort", "off", { openai: { reasoningEffort: "none" } }],
    ["openai-effort", "low", { openai: { reasoningEffort: "low" } }],
    ["openai-effort", "medium", { openai: { reasoningEffort: "medium" } }],
    ["openai-effort", "high", { openai: { reasoningEffort: "high" } }],

    [
      "anthropic-adaptive",
      "off",
      { anthropic: { thinking: { type: "disabled" } } },
    ],
    [
      "anthropic-adaptive",
      "low",
      { anthropic: { thinking: { type: "adaptive" }, effort: "low" } },
    ],
    [
      "anthropic-adaptive",
      "medium",
      { anthropic: { thinking: { type: "adaptive" }, effort: "medium" } },
    ],
    [
      "anthropic-adaptive",
      "high",
      { anthropic: { thinking: { type: "adaptive" }, effort: "high" } },
    ],

    [
      "anthropic-budget",
      "off",
      { anthropic: { thinking: { type: "disabled" } } },
    ],
    [
      "anthropic-budget",
      "low",
      { anthropic: { thinking: { type: "enabled", budgetTokens: 2048 } } },
    ],
    [
      "anthropic-budget",
      "medium",
      { anthropic: { thinking: { type: "enabled", budgetTokens: 8192 } } },
    ],
    [
      "anthropic-budget",
      "high",
      { anthropic: { thinking: { type: "enabled", budgetTokens: 16384 } } },
    ],

    [
      "gemini-level",
      "off",
      { google: { thinkingConfig: { thinkingLevel: "minimal" } } },
    ],
    [
      "gemini-level",
      "low",
      { google: { thinkingConfig: { thinkingLevel: "low" } } },
    ],
    [
      "gemini-level",
      "medium",
      { google: { thinkingConfig: { thinkingLevel: "medium" } } },
    ],
    [
      "gemini-level",
      "high",
      { google: { thinkingConfig: { thinkingLevel: "high" } } },
    ],

    [
      "gemini-budget",
      "off",
      { google: { thinkingConfig: { thinkingBudget: 0 } } },
    ],
    [
      "gemini-budget",
      "low",
      { google: { thinkingConfig: { thinkingBudget: 1024 } } },
    ],
    [
      "gemini-budget",
      "medium",
      { google: { thinkingConfig: { thinkingBudget: 8192 } } },
    ],
    [
      "gemini-budget",
      "high",
      { google: { thinkingConfig: { thinkingBudget: 24576 } } },
    ],
  ])("%s + %s", (kind, effort, expected) => {
    expect(
      toReasoningOptions(
        kind,
        effort as Parameters<typeof toReasoningOptions>[1],
      ),
    ).toEqual(expected);
  });
});

describe("getReasoningOptions", () => {
  it("uses the model's reasoning kind", () => {
    expect(getReasoningOptions("anthropic", "claude-sonnet-5", "high")).toEqual(
      {
        anthropic: { thinking: { type: "adaptive" }, effort: "high" },
      },
    );
    expect(getReasoningOptions("google", "gemini-2.5-flash", "off")).toEqual({
      google: { thinkingConfig: { thinkingBudget: 0 } },
    });
  });

  it("returns no options for a model off the allowlist", () => {
    expect(getReasoningOptions("openai", "gpt-unknown", "high")).toEqual({});
  });
});
