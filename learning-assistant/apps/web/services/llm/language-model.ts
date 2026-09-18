import { anthropic } from "@ai-sdk/anthropic";
import { google } from "@ai-sdk/google";
import { openai } from "@ai-sdk/openai";
import type { Provider } from "@repo/shared/schemas";
import type { LanguageModel } from "ai";

// The default provider instances read OPENAI_API_KEY, ANTHROPIC_API_KEY and
// GOOGLE_GENERATIVE_AI_API_KEY, the same keys as `PROVIDER_CATALOG`.
const providerFactories = {
  openai,
  anthropic,
  google,
} satisfies Record<Provider, (modelId: string) => LanguageModel>;

export const createLanguageModel = (
  provider: Provider,
  modelId: string,
): LanguageModel => providerFactories[provider](modelId);
