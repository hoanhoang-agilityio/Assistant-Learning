import type { Draft } from "@repo/shared/schemas";

import { FeedbackDraft } from "@/features/canvas/components/FeedbackDraft";
import { MarkdownPreview } from "@/features/canvas/components/MarkdownPreview";
import { QuizDraftStage } from "@/features/canvas/components/QuizDraftStage";
import { EvaluationStage } from "@/features/canvas/components/stages/EvaluationStage";
import { ResearchStage } from "@/features/canvas/components/stages/ResearchStage";
import { ScoreStage } from "@/features/canvas/components/stages/ScoreStage";
import { StreamingNote } from "@/features/canvas/components/StreamingNote";
import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import type { CanvasStage, StageStep } from "@/features/canvas/types/canvas";

export interface StageDraftProps {
  stage: CanvasStage;
  step: StageStep;
  draft: Draft;
}

const DraftBody = ({ stage, draft }: Omit<StageDraftProps, "step">) => {
  switch (draft.task) {
    case "research":
      return <ResearchStage research={draft.research} />;
    case "material":
    case "simplify":
      return (
        <section className={CARD_CLASS}>
          <MarkdownPreview markdown={draft.markdown} />
        </section>
      );
    case "quiz":
      return <QuizDraftStage questions={draft.questions} />;
    case "evaluate":
      return stage === "evaluation" ? (
        <EvaluationStage evaluation={draft.evaluation} />
      ) : stage === "score" ? (
        <ScoreStage score={draft.score} evaluation={draft.evaluation} />
      ) : (
        <FeedbackDraft feedback={draft.feedback} />
      );
  }
};

/** A stage whose subagent is still writing: its output so far. */
export const StageDraft = ({ stage, step, draft }: StageDraftProps) => (
  <div className="space-y-3" aria-busy="true">
    <StreamingNote label={`Writing ${step.title}…`} />
    <DraftBody stage={stage} draft={draft} />
  </div>
);
