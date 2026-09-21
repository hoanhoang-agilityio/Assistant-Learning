import type { AnthropicLanguageModelOptions } from "@ai-sdk/anthropic";
import type { GoogleLanguageModelOptions } from "@ai-sdk/google";
import type { OpenAILanguageModelResponsesOptions } from "@ai-sdk/openai";
import type { Provider, ReasoningEffort } from "@repo/shared/schemas";

import {
  ANTHROPIC_THINKING_BUDGET,
  GEMINI_THINKING_BUDGET,
  GEMINI_THINKING_LEVEL,
} from "@/constants/reasoning";
import type { ProviderOptions, ReasoningKind } from "@/types/llm";
import { findModel } from "@/utils/models";

/** Maps the normalised effort to one reasoning kind's `providerOptions`. */
export const toReasoningOptions = (
  kind: ReasoningKind,
  effort: ReasoningEffort,
): ProviderOptions => {
  switch (kind) {
    case "openai-effort":
      return {
        openai: {
          reasoningEffort: effort === "off" ? "none" : effort,
        } satisfies OpenAILanguageModelResponsesOptions,
      };
    case "anthropic-adaptive":
      return {
        anthropic: (effort === "off"
          ? { thinking: { type: "disabled" } }
          : {
              thinking: { type: "adaptive" },
              effort,
            }) satisfies AnthropicLanguageModelOptions,
      };
    case "anthropic-budget":
      return {
        anthropic: {
          thinking:
            effort === "off"
              ? { type: "disabled" }
              : {
                  type: "enabled",
                  budgetTokens: ANTHROPIC_THINKING_BUDGET[effort],
                },
        } satisfies AnthropicLanguageModelOptions,
      };
    case "gemini-level":
      return {
        google: {
          thinkingConfig: { thinkingLevel: GEMINI_THINKING_LEVEL[effort] },
        } satisfies GoogleLanguageModelOptions,
      };
    case "gemini-budget":
      return {
        google: {
          thinkingConfig: { thinkingBudget: GEMINI_THINKING_BUDGET[effort] },
        } satisfies GoogleLanguageModelOptions,
      };
  }
};

/**
 * `providerOptions` for the chosen model and effort. Returns `{}` for models
 * that are not on the allowlist or have no reasoning control, so the provider
 * default applies.
 */
export const getReasoningOptions = (
  provider: Provider,
  modelId: string,
  effort: ReasoningEffort,
): ProviderOptions => {
  const kind = findModel(provider, modelId)?.reasoning;
  return kind ? toReasoningOptions(kind, effort) : {};
};
