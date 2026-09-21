import type { SurfaceTemplate } from "@repo/shared/a2ui/surface-template";
import type { ResearchResult } from "@repo/shared/schemas";

import {
  A2UI_VERSION,
  DATA_MODEL_ROOT,
} from "@/features/canvas/constants/a2ui";
import type {
  A2UIMessage,
  ResearchDataModel,
} from "@/features/canvas/types/a2ui";

/** `createSurface` + `updateComponents`: the fixed part of a surface. */
export const createSurfaceMessages = ({
  surfaceId,
  catalogId,
  components,
}: SurfaceTemplate): A2UIMessage[] => [
  { version: A2UI_VERSION, createSurface: { surfaceId, catalogId } },
  { version: A2UI_VERSION, updateComponents: { surfaceId, components } },
];

/** `updateDataModel` replacing the whole data model with the stage's data. */
export const createDataModelMessage = (
  surfaceId: string,
  dataModel: object,
): A2UIMessage => ({
  version: A2UI_VERSION,
  updateDataModel: { surfaceId, path: DATA_MODEL_ROOT, value: dataModel },
});

/** Every message that renders `template` with `dataModel`, in order. */
export const buildSurface = (
  template: SurfaceTemplate,
  dataModel: object,
): A2UIMessage[] => [
  ...createSurfaceMessages(template),
  createDataModelMessage(template.surfaceId, dataModel),
];

/** The Research template's data model; its bindings read `/research/…`. */
export const createResearchDataModel = (
  research: ResearchResult,
): ResearchDataModel => ({ research });
