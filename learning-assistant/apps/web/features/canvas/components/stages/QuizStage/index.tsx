import type { Evaluation, Quiz } from "@repo/shared/schemas";

import { QuizStageView } from "@/features/canvas/components/stages/QuizStageView";
import { useQuizStage } from "@/features/canvas/hooks/use-quiz-stage";

export interface QuizStageProps {
  quiz: Quiz;
  /** Shown on the question cards once the quiz is submitted. */
  evaluation: Evaluation | null;
}

/** The Quiz stage: the fixed quiz surface, bound to `state.quiz`. */
export const QuizStage = ({ quiz, evaluation }: QuizStageProps) => {
  const { dataModel, handleAction } = useQuizStage(quiz, evaluation);

  return <QuizStageView dataModel={dataModel} onAction={handleAction} />;
};
