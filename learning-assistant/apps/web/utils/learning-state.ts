import {
  initialLearningState,
  type LearningState,
  LearningStateSchema,
} from "@repo/shared/schemas";

/**
 * Reads the client's state. Missing keys are filled from the initial state,
 * and a state that still fails validation is replaced by the initial state.
 */
export const readLearningState = (raw: unknown): LearningState => {
  const merged =
    raw && typeof raw === "object"
      ? { ...initialLearningState, ...raw }
      : initialLearningState;
  const parsed = LearningStateSchema.safeParse(merged);
  return parsed.success ? parsed.data : initialLearningState;
};
