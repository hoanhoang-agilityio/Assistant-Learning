import type { PropsOf, RendererProps } from "@copilotkit/a2ui-renderer";
import type { ResearchResult } from "@repo/shared/schemas";

import type { CANVAS_COMPONENT_DEFINITIONS } from "@/features/canvas/constants/a2ui-catalog";

export type CanvasComponentName = keyof typeof CANVAS_COMPONENT_DEFINITIONS;

/** What the A2UI renderer passes to a canvas catalog component. */
export type CanvasComponentProps<K extends CanvasComponentName> = RendererProps<
  PropsOf<typeof CANVAS_COMPONENT_DEFINITIONS, K>
>;

/** An A2UI v0.9 server-to-client message, as the renderer processes it. */
export type A2UIMessage = { version: "v0.9" } & (
  | { createSurface: { surfaceId: string; catalogId: string } }
  | { updateComponents: { surfaceId: string; components: object[] } }
  | { updateDataModel: { surfaceId: string; path: string; value: unknown } }
);

export interface ResearchDataModel {
  research: ResearchResult;
}
