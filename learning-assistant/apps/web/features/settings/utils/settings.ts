import {
  type Provider,
  QUESTION_COUNT,
  type Settings,
  SettingsSchema,
} from "@repo/shared/schemas";

import { DEFAULT_SETTINGS } from "@/constants/settings";
import {
  getDefaultModel,
  isAllowedModel,
  supportsReasoning,
} from "@/utils/models";

/**
 * Reads persisted settings. Each field that is missing or invalid falls back
 * to its default, so one bad field does not reset the rest, and a model off
 * the provider's allowlist falls back to the provider's default model.
 */
export const parseSettings = (raw: unknown): Settings => {
  const input = raw && typeof raw === "object" ? raw : {};
  const shape = SettingsSchema.shape;
  const pick = <K extends keyof Settings>(key: K): Settings[K] => {
    const parsed = shape[key].safeParse(
      (input as Record<string, unknown>)[key],
    );
    return parsed.success
      ? (parsed.data as Settings[K])
      : DEFAULT_SETTINGS[key];
  };

  const provider = pick("provider");
  const requestedModel = pick("model");
  const model = isAllowedModel(provider, requestedModel)
    ? requestedModel
    : getDefaultModel(provider).id;

  return withSupportedEffort({
    provider,
    model,
    reasoningEffort: pick("reasoningEffort"),
    questionCount: pick("questionCount"),
    learningLevel: pick("learningLevel"),
    theme: pick("theme"),
  });
};

/** Turns reasoning off for a model without a reasoning control. */
const withSupportedEffort = (settings: Settings): Settings => {
  return supportsReasoning(settings.provider, settings.model)
    ? settings
    : { ...settings, reasoningEffort: "off" };
};

/** Switches provider and moves to its default model. */
export const selectProvider = (
  settings: Settings,
  provider: Provider,
): Settings => {
  if (provider === settings.provider) return settings;
  return withSupportedEffort({
    ...settings,
    provider,
    model: getDefaultModel(provider).id,
  });
};

/** Switches model within the current provider; ignores models off the allowlist. */
export const selectModel = (settings: Settings, model: string): Settings => {
  if (!isAllowedModel(settings.provider, model)) return settings;
  return withSupportedEffort({ ...settings, model });
};

export const clampQuestionCount = (count: number): number => {
  if (!Number.isFinite(count)) return QUESTION_COUNT.default;
  return Math.min(
    QUESTION_COUNT.max,
    Math.max(QUESTION_COUNT.min, Math.round(count)),
  );
};

/**
 * Moves to the first available provider when the chosen one has no key on the
 * server. Returns the settings unchanged when nothing is available, so the
 * server can explain the missing keys.
 */
export const reconcileProvider = (
  settings: Settings,
  available: readonly Provider[],
): Settings => {
  const [firstAvailable] = available;
  if (!firstAvailable || available.includes(settings.provider)) return settings;
  return selectProvider(settings, firstAvailable);
};
