import type { OpenAILanguageModelResponsesOptions } from "@ai-sdk/openai";

/** The model every agent uses. */
export const OPENAI_MODEL = "gpt-5.4-mini";

/** `providerOptions` for every model call: low reasoning effort. */
export const OPENAI_CALL_OPTIONS = {
  openai: {
    reasoningEffort: "low",
  } satisfies OpenAILanguageModelResponsesOptions,
};
