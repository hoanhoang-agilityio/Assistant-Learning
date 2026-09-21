import {
  initialLearningState,
  type LearningState,
  LearningStateSchema,
  type Notes,
  QUIZ_STATE_KEYS,
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

/** The notes text the student is looking at: simplified or original. */
export const getActiveNotes = (notes: Notes): string =>
  notes.view === "simplified" && notes.simplified !== null
    ? notes.simplified
    : notes.original;

/** A quiz or anything built from it exists. */
export const hasQuizData = (state: LearningState): boolean =>
  QUIZ_STATE_KEYS.some((key) => state[key] !== null);
