import type { QuestionDraft } from "@repo/shared/schemas";
import { useMemo } from "react";

import { createQuizDraftDataModel } from "@/features/canvas/utils/build-surface";

/** The Quiz surface's data model while the questions are written. */
export const useQuizDraftStage = (questions: QuestionDraft[]) => {
  const dataModel = useMemo(
    () => createQuizDraftDataModel(questions),
    [questions],
  );
  return { dataModel };
};
