import { QUESTION_COUNT, type Settings } from "@repo/shared/schemas";

import { DEFAULT_PROVIDER, PROVIDER_CATALOG } from "./models";

export const DEFAULT_SETTINGS: Settings = {
  provider: DEFAULT_PROVIDER,
  model: PROVIDER_CATALOG[DEFAULT_PROVIDER].models[0].id,
  reasoningEffort: "low",
  questionCount: QUESTION_COUNT.default,
  learningLevel: "beginner",
  theme: "light",
};
