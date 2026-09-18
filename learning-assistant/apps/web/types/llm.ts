import type { generateText } from "ai";

/**
 * How a model exposes reasoning. The reasoning mapper
 * (`services/llm/reasoning.ts`) switches on this to build `providerOptions`.
 * `null` means the model has no reasoning control and the effort picker is
 * disabled.
 */
export type ReasoningKind =
  | "openai-effort"
  | "anthropic-adaptive"
  | "anthropic-budget"
  | "gemini-level"
  | "gemini-budget";

export interface ModelInfo {
  id: string;
  label: string;
  reasoning: ReasoningKind | null;
}

export interface ProviderInfo {
  label: string;
  /** Server env variable holding the API key. */
  envKey: string;
  /** First entry is the provider's default model. */
  models: readonly ModelInfo[];
}

/** The `providerOptions` accepted by AI SDK calls. */
export type ProviderOptions = NonNullable<
  Parameters<typeof generateText>[0]["providerOptions"]
>;
