import { DEFAULT_SETTINGS } from "@repo/shared/constants/settings";
import type { QuizDraft } from "@repo/shared/schemas";

import type { RunSettings } from "../../types/llm";

/** Text that must never reach the client before the quiz is submitted. */
export const SECRET_EXPLANATION = "SECRET-EXPLANATION";

export const QUIZ_DRAFT: QuizDraft = {
  questions: [0, 1, 2].map((index) => ({
    concept: index === 2 ? "Scope" : "Closures",
    question: `Question ${index + 1}?`,
    options: ["a", "b", "c", "d"],
    correctIndex: index + 1,
    explanation: `${SECRET_EXPLANATION}-${index + 1}`,
  })),
};

/** Run settings with a placeholder key; model calls are mocked in tests. */
export const TEST_RUN_SETTINGS: RunSettings = {
  ...DEFAULT_SETTINGS,
  apiKey: "sk-test",
};
