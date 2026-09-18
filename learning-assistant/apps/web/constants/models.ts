import type { Provider } from "@repo/shared/schemas";

import type { ProviderInfo } from "../types/llm";

// TODO: configure these in the .env
export const PROVIDER_CATALOG = {
  openai: {
    label: "OpenAI",
    envKey: "OPENAI_API_KEY",
    models: [
      { id: "gpt-5.4-mini", label: "GPT-5.4 mini", reasoning: "openai-effort" },
      { id: "gpt-5.4", label: "GPT-5.4", reasoning: "openai-effort" },
    ],
  },
  anthropic: {
    label: "Anthropic",
    envKey: "ANTHROPIC_API_KEY",
    models: [
      {
        id: "claude-sonnet-5",
        label: "Claude Sonnet 5",
        reasoning: "anthropic-adaptive",
      },
      {
        id: "claude-haiku-4-5",
        label: "Claude Haiku 4.5",
        reasoning: "anthropic-budget",
      },
    ],
  },
  google: {
    label: "Google",
    envKey: "GOOGLE_GENERATIVE_AI_API_KEY",
    models: [
      {
        id: "gemini-3.8-flash",
        label: "Gemini 3.8 Flash",
        reasoning: "gemini-level",
      },
      {
        id: "gemini-2.5-flash",
        label: "Gemini 2.5 Flash",
        reasoning: "gemini-budget",
      },
    ],
  },
} as const satisfies Record<Provider, ProviderInfo>;

export const DEFAULT_PROVIDER = "openai" satisfies Provider;
