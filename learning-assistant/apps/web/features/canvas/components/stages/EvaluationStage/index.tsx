import { EVALUATION_TEMPLATE } from "@repo/shared/a2ui/templates";
import type { Evaluation } from "@repo/shared/schemas";

import { CanvasSurface } from "@/features/canvas/components/CanvasSurface";
import { useEvaluationStage } from "@/features/canvas/hooks/use-evaluation-stage";

export interface EvaluationStageProps {
  evaluation: Evaluation;
}

/** The Evaluation stage: the fixed stats surface, bound to `state.evaluation`. */
export const EvaluationStage = ({ evaluation }: EvaluationStageProps) => {
  const { dataModel } = useEvaluationStage(evaluation);
  return <CanvasSurface template={EVALUATION_TEMPLATE} dataModel={dataModel} />;
};
