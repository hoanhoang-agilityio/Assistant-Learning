import type { Evaluation, Score } from "@repo/shared/schemas";
import { useMemo } from "react";

import { createScoreDataModel } from "@/features/canvas/utils/build-surface";

/** The Score surface's data model, rebuilt when the score changes. */
export const useScoreStage = (score: Score, evaluation: Evaluation) => {
  const dataModel = useMemo(
    () => createScoreDataModel(score, evaluation),
    [score, evaluation],
  );
  return { dataModel };
};
