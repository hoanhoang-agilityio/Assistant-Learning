import type { ResearchResult } from "@repo/shared/schemas";
import { useMemo } from "react";

import { createResearchDataModel } from "@/features/canvas/utils/build-surface";

/**
 * The Research surface's data model. Rebuilt only when the research changes,
 * so the surface gets one `updateDataModel` per state update.
 */
export const useResearchStage = (research: ResearchResult) => {
  const dataModel = useMemo(
    () => createResearchDataModel(research),
    [research],
  );
  return { dataModel };
};
