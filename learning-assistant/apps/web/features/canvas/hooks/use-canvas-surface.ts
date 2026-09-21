import { useA2UIActions, useA2UIError } from "@copilotkit/a2ui-renderer";
import type { SurfaceTemplate } from "@repo/shared/a2ui/surface-template";
import { useEffect } from "react";

import {
  createDataModelMessage,
  createSurfaceMessages,
} from "@/features/canvas/utils/build-surface";

/**
 * Feeds a fixed surface to the enclosing `A2UIProvider`: the template once,
 * then the data model on every change, so each state update re-renders the
 * bound components. Returns the renderer's error, if any.
 */
export const useCanvasSurface = (
  template: SurfaceTemplate,
  dataModel: object,
) => {
  const { processMessages, getSurface } = useA2UIActions();

  // Guarded because Strict Mode runs effects twice and a surface can only be
  // created once.
  useEffect(() => {
    if (!getSurface(template.surfaceId)) {
      processMessages(createSurfaceMessages(template));
    }
  }, [template, getSurface, processMessages]);

  useEffect(() => {
    processMessages([createDataModelMessage(template.surfaceId, dataModel)]);
  }, [template.surfaceId, dataModel, processMessages]);

  return { error: useA2UIError() };
};
