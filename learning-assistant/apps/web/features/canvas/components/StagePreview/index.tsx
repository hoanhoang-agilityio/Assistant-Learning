import type { LearningState } from "@repo/shared/schemas";
import { Lightbulb } from "lucide-react";

import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import type { CanvasStage } from "@/features/canvas/types/canvas";

export interface StagePreviewProps {
  stage: CanvasStage;
  state: LearningState;
}

/**
 * A plain read-only view of each stage's data. The real stage views replace
 * it: Research and Notes in M3, Quiz in M4, Evaluation to Feedback in M5.
 */
export const StagePreview = ({ stage, state }: StagePreviewProps) => {
  switch (stage) {
    case "research": {
      if (!state.research) return null;
      const { title, summary, keyInsight } = state.research;
      return (
        <article className={CARD_CLASS}>
          <span className="text-xs font-semibold tracking-wider text-indigo-500 uppercase">
            Curated Reading
          </span>
          <h3 className="mt-2 mb-2 text-lg font-bold">{title}</h3>
          <p className="mb-4 text-xs leading-relaxed whitespace-pre-wrap text-slate-600 dark:text-slate-300">
            {summary}
          </p>
          <div className="flex items-start gap-3 rounded-xl border border-indigo-100 bg-indigo-50/50 p-4 text-xs text-indigo-900 dark:border-indigo-900/50 dark:bg-indigo-950/30 dark:text-indigo-200">
            <Lightbulb className="mt-0.5 h-5 w-5 shrink-0 text-indigo-500" />
            <p>
              <strong>Key Insight:</strong> {keyInsight}
            </p>
          </div>
        </article>
      );
    }
    case "notes": {
      if (!state.notes) return null;
      const { original, simplified, view } = state.notes;
      return (
        <pre
          className={`${CARD_CLASS} overflow-x-auto font-mono text-xs leading-relaxed whitespace-pre-wrap`}
        >
          {view === "simplified" && simplified ? simplified : original}
        </pre>
      );
    }
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
