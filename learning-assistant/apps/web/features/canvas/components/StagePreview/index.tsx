import type { LearningState } from "@repo/shared/schemas";

import { NotesStage } from "@/features/canvas/components/stages/NotesStage";
import { ResearchStage } from "@/features/canvas/components/stages/ResearchStage";
import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import type { CanvasStage } from "@/features/canvas/types/canvas";

export interface StagePreviewProps {
  stage: CanvasStage;
  state: LearningState;
}

/**
 * The view of each stage's data. Research and Notes have their real views;
 * the rest are plain read-only placeholders until M4 (Quiz) and M5
 * (Evaluation to Feedback).
 */
export const StagePreview = ({ stage, state }: StagePreviewProps) => {
  switch (stage) {
    case "research":
      return state.research && <ResearchStage research={state.research} />;
    case "notes":
      return state.notes && <NotesStage notes={state.notes} />;
    case "quiz":
      if (!state.quiz) return null;
      return (
        <p className={`${CARD_CLASS} text-sm`}>
          {state.quiz.questions.length} questions ready.
        </p>
      );
    case "evaluation":
      if (!state.evaluation) return null;
      return (
        <p className={`${CARD_CLASS} text-sm`}>
          {state.evaluation.correct} / {state.evaluation.total} correct (
          {state.evaluation.percent}%).
        </p>
      );
    case "score":
      if (!state.score) return null;
      return (
        <p className={`${CARD_CLASS} text-sm`}>
          {state.score.tier} · {state.score.percent}%
        </p>
      );
    case "feedback":
      if (!state.feedback) return null;
      return (
        <p className={`${CARD_CLASS} text-sm whitespace-pre-wrap`}>
          {state.feedback.summary}
        </p>
      );
  }
};
