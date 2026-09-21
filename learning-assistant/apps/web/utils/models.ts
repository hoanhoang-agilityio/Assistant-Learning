import type { Provider } from "@repo/shared/schemas";

import { PROVIDER_CATALOG } from "@/constants/models";
import type { ModelInfo } from "@/types/llm";

export const getModels = (provider: Provider): readonly ModelInfo[] => {
  return PROVIDER_CATALOG[provider].models;
};

export const getDefaultModel = (provider: Provider): ModelInfo => {
  return PROVIDER_CATALOG[provider].models[0];
};

/** Returns the model if it is on the provider's allowlist, else `undefined`. */
export const findModel = (
  provider: Provider,
  modelId: string,
): ModelInfo | undefined => {
  return getModels(provider).find((m) => m.id === modelId);
};

export const isAllowedModel = (
  provider: Provider,
  modelId: string,
): boolean => {
  return findModel(provider, modelId) !== undefined;
};

export const supportsReasoning = (
  provider: Provider,
  modelId: string,
): boolean => {
  return findModel(provider, modelId)?.reasoning != null;
};
