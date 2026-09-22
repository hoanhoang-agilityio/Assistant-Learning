import { SCORE_TEMPLATE } from "@repo/shared/a2ui/templates";
import type { Evaluation, Score } from "@repo/shared/schemas";

import { CanvasSurface } from "@/features/canvas/components/CanvasSurface";
import { useScoreStage } from "@/features/canvas/hooks/use-score-stage";

export interface ScoreStageProps {
  score: Score;
  evaluation: Evaluation;
}

/** The Score stage: the fixed tier surface, bound to `state.score`. */
export const ScoreStage = ({ score, evaluation }: ScoreStageProps) => {
  const { dataModel } = useScoreStage(score, evaluation);
  return <CanvasSurface template={SCORE_TEMPLATE} dataModel={dataModel} />;
};
