import {
  initialLearningState,
  type LearningState,
  LearningStateSchema,
  type Material,
  QUIZ_STATE_KEYS,
} from "../schemas";

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

/** The learning material text the student is looking at: simplified or original. */
export const getActiveMaterial = (material: Material): string =>
  material.view === "simplified" && material.simplified !== null
    ? material.simplified
    : material.original;

/** A quiz or anything built from it exists. */
export const hasQuizData = (state: LearningState): boolean =>
  QUIZ_STATE_KEYS.some((key) => state[key] !== null);

/** Learning material or a quiz exists, so a new topic would throw work away. */
export const hasTopicWork = (state: LearningState): boolean =>
  state.material !== null || hasQuizData(state);
