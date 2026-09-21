import { A2UIProvider, type OnActionCallback } from "@copilotkit/a2ui-renderer";
import type { SurfaceTemplate } from "@repo/shared/a2ui/surface-template";

import { CanvasSurfaceBody } from "@/features/canvas/components/CanvasSurfaceBody";
import { CANVAS_CATALOG } from "@/features/canvas/constants/a2ui-catalog";

export interface CanvasSurfaceProps {
  template: SurfaceTemplate;
  /** The stage's data; the template's bindings read from it. */
  dataModel: object;
  /** Called when a component dispatches an action (a button press). */
  onAction?: OnActionCallback;
}

/** A fixed A2UI surface rendered with the canvas catalog. */
export const CanvasSurface = ({
  template,
  dataModel,
  onAction,
}: CanvasSurfaceProps) => (
  <A2UIProvider catalog={CANVAS_CATALOG} onAction={onAction}>
    <CanvasSurfaceBody template={template} dataModel={dataModel} />
  </A2UIProvider>
);
