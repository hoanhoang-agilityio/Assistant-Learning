import type { Evaluation } from "@repo/shared/schemas";
import { useMemo } from "react";

import { createEvaluationDataModel } from "@/features/canvas/utils/build-surface";

/** The Evaluation surface's data model, rebuilt when the evaluation changes. */
export const useEvaluationStage = (evaluation: Evaluation) => {
  const dataModel = useMemo(
    () => createEvaluationDataModel(evaluation),
    [evaluation],
  );
  return { dataModel };
};
