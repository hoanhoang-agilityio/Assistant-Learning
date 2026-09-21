import type { A2UIClientEventMessage } from "@copilotkit/a2ui-renderer";
import { QUIZ_TEMPLATE } from "@repo/shared/a2ui/templates";

import { CanvasSurface } from "@/features/canvas/components/CanvasSurface";
import type { QuizDataModel } from "@/features/canvas/types/a2ui";

export interface QuizStageViewProps {
  dataModel: QuizDataModel;
  onAction: (message: A2UIClientEventMessage) => void;
}

/** The fixed quiz surface: question cards, then Submit, Retake, New questions. */
export const QuizStageView = ({ dataModel, onAction }: QuizStageViewProps) => (
  <CanvasSurface
    template={QUIZ_TEMPLATE}
    dataModel={dataModel}
    onAction={onAction}
  />
);
