import type { Provider } from "@repo/shared/schemas";

import { PROVIDER_CATALOG } from "../constants/models";
import type { ModelInfo } from "../types/llm";

export function getModels(provider: Provider): readonly ModelInfo[] {
  return PROVIDER_CATALOG[provider].models;
}

export function getDefaultModel(provider: Provider): ModelInfo {
  return PROVIDER_CATALOG[provider].models[0];
}

/** Returns the model if it is on the provider's allowlist, else `undefined`. */
export function findModel(
  provider: Provider,
  modelId: string,
): ModelInfo | undefined {
  return getModels(provider).find((m) => m.id === modelId);
}

export function isAllowedModel(provider: Provider, modelId: string): boolean {
  return findModel(provider, modelId) !== undefined;
}

export function supportsReasoning(
  provider: Provider,
  modelId: string,
): boolean {
  return findModel(provider, modelId)?.reasoning != null;
}
