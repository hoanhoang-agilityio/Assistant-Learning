import type { LearningState } from "@repo/shared/schemas";

import { EvaluationStage } from "@/features/canvas/components/stages/EvaluationStage";
import { FeedbackStage } from "@/features/canvas/components/stages/FeedbackStage";
import { MaterialStage } from "@/features/canvas/components/stages/MaterialStage";
import { QuizStage } from "@/features/canvas/components/stages/QuizStage";
import { ResearchStage } from "@/features/canvas/components/stages/ResearchStage";
import { ScoreStage } from "@/features/canvas/components/stages/ScoreStage";
import type { CanvasStage } from "@/features/canvas/types/canvas";

export interface StagePreviewProps {
  stage: CanvasStage;
  state: LearningState;
}

/** The view of each stage's data. */
export const StagePreview = ({ stage, state }: StagePreviewProps) => {
  switch (stage) {
    case "research":
      return state.research && <ResearchStage research={state.research} />;
    case "material":
      return state.material && <MaterialStage material={state.material} />;
    case "quiz":
      return (
        state.quiz && (
          <QuizStage quiz={state.quiz} evaluation={state.evaluation} />
        )
      );
    case "evaluation":
      return (
        state.evaluation && <EvaluationStage evaluation={state.evaluation} />
      );
    case "score":
      return (
        state.score &&
        state.evaluation && (
          <ScoreStage score={state.score} evaluation={state.evaluation} />
        )
      );
    case "feedback":
      return (
        state.feedback && (
          <FeedbackStage
            feedback={state.feedback}
            reflection={state.reflection}
          />
        )
      );
  }
};
