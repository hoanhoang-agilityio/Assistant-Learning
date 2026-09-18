import {
  initialLearningState,
  type LearningState,
  LearningStateSchema,
} from "@repo/shared/schemas";

import type { SupervisorState } from "../../types/agents";

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

/** Trims the state to what the Supervisor needs to choose the next step. */
export const toSupervisorState = ({
  stage,
  status,
  topic,
  research,
  notes,
  quiz,
  score,
  feedback,
  reflection,
}: LearningState): SupervisorState => ({
  stage,
  status,
  topic,
  research: research && {
    title: research.title,
    keyInsight: research.keyInsight,
  },
  notes: notes && {
    view: notes.view,
    hasSimplified: notes.simplified !== null,
    characters: (notes.view === "simplified" && notes.simplified
      ? notes.simplified
      : notes.original
    ).length,
  },
  quiz: quiz && {
    questionCount: quiz.questions.length,
    answeredCount: Object.keys(quiz.answers).length,
    submitted: quiz.submitted,
  },
  score,
  hasFeedback: feedback !== null,
  hasReflection: reflection !== null,
});
