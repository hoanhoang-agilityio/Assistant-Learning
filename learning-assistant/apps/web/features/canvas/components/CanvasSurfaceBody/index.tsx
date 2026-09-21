import { A2UIRenderer } from "@copilotkit/a2ui-renderer";
import type { SurfaceTemplate } from "@repo/shared/a2ui/surface-template";

import { StageError } from "@/features/canvas/components/StageError";
import { useCanvasSurface } from "@/features/canvas/hooks/use-canvas-surface";

export interface CanvasSurfaceBodyProps {
  template: SurfaceTemplate;
  dataModel: object;
}

/** Sends the surface to the provider above it and renders it. */
export const CanvasSurfaceBody = ({
  template,
  dataModel,
}: CanvasSurfaceBodyProps) => {
  const { error } = useCanvasSurface(template, dataModel);

  return error ? (
    <StageError message={`This stage could not be drawn: ${error}`} />
  ) : (
    <A2UIRenderer surfaceId={template.surfaceId} />
  );
};
