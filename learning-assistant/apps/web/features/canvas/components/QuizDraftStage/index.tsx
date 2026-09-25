import type { QuestionDraft } from "@repo/shared/schemas";

import { QuizStageView } from "@/features/canvas/components/stages/QuizStageView";
import { useQuizDraftStage } from "@/features/canvas/hooks/use-quiz-draft-stage";

export interface QuizDraftStageProps {
  questions: QuestionDraft[];
}

/** The quiz surface, locked, with the questions written so far. */
export const QuizDraftStage = ({ questions }: QuizDraftStageProps) => {
  const { dataModel } = useQuizDraftStage(questions);
  return <QuizStageView dataModel={dataModel} />;
};
