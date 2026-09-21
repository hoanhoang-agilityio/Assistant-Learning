import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import {
  type LearningState,
  OptionIndexSchema,
  QUIZ_STATE_KEYS,
} from "@repo/shared/schemas";
import { z } from "zod";

import type { SelectAnswer } from "@/features/canvas/types/quiz";

/** The context a QuestionCard sends when an option is picked. */
const SelectAnswerSchema = z.object({
  questionId: z.string().min(1),
  optionIndex: OptionIndexSchema,
});

/** The `select_answer` action a QuestionCard dispatches for one option. */
export const createSelectAnswerAction = (choice: SelectAnswer) => ({
  event: { name: QUIZ_ACTIONS.selectAnswer, context: { ...choice } },
});

export const parseSelectAnswer = (context: unknown): SelectAnswer | null => {
  const parsed = SelectAnswerSchema.safeParse(context);
  return parsed.success ? parsed.data : null;
};

/**
 * Records the student's choice for one question. Returns the same state when
 * nothing changes: no quiz, already graded, an unknown question, or the same
 * option again.
 */
export const selectAnswer = (
  state: LearningState,
  { questionId, optionIndex }: SelectAnswer,
): LearningState => {
  const { quiz } = state;
  if (
    !quiz ||
    quiz.submitted ||
    quiz.answers[questionId] === optionIndex ||
    !quiz.questions.some(({ id }) => id === questionId)
  ) {
    return state;
  }
  return {
    ...state,
    quiz: { ...quiz, answers: { ...quiz.answers, [questionId]: optionIndex } },
  };
};

/**
 * Retake: the same questions with no answers. The last attempt's results are
 * cleared and the canvas goes back to the Quiz stage.
 */
export const retakeQuiz = (state: LearningState): LearningState => {
  const { quiz } = state;
  if (!quiz) return state;

  return {
    ...state,
    ...Object.fromEntries(
      QUIZ_STATE_KEYS.filter((key) => key !== "quiz").map((key) => [key, null]),
    ),
    quiz: { ...quiz, answers: {}, submitted: false },
    stage: "quiz",
  };
};
