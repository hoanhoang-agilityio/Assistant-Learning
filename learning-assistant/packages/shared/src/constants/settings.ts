import { QUESTION_COUNT, type Settings } from "../schemas";

export const DEFAULT_SETTINGS: Settings = {
  questionCount: QUESTION_COUNT.default,
  learningLevel: "beginner",
  theme: "system",
};
