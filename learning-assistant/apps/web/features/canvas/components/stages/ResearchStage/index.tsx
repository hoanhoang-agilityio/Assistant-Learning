import { RESEARCH_TEMPLATE } from "@repo/shared/a2ui/templates";
import type { ResearchResult } from "@repo/shared/schemas";

import { CanvasSurface } from "@/features/canvas/components/CanvasSurface";
import { useResearchStage } from "@/features/canvas/hooks/use-research-stage";

export interface ResearchStageProps {
  research: ResearchResult;
}

/** The Research stage: the fixed research surface, bound to `state.research`. */
export const ResearchStage = ({ research }: ResearchStageProps) => {
  const { dataModel } = useResearchStage(research);
  return <CanvasSurface template={RESEARCH_TEMPLATE} dataModel={dataModel} />;
};
