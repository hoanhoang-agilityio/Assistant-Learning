import { useA2UIActions, useA2UIError } from "@copilotkit/a2ui-renderer";
import type { BoardSurface } from "@repo/shared/schemas";
import { useEffect, useMemo } from "react";

import { parseSurfaceOperations } from "@/features/canvas/utils/a2ui-operations";

/**
 * Sends a Board view's operations to the enclosing `A2UIProvider` once. The
 * state is re-read on every render, so the operations are compared by value.
 * Returns an error when they are rejected, by the parser or the renderer.
 */
export const useBoardSurface = ({ id, operations }: BoardSurface) => {
  const { processMessages, getSurface } = useA2UIActions();
  const key = JSON.stringify(operations);
  const parsed = useMemo(
    () => parseSurfaceOperations(JSON.parse(key) as unknown[], id),
    [key, id],
  );

  // Guarded because Strict Mode runs effects twice and a surface can only be
  // created once.
  useEffect(() => {
    if (parsed.length > 0 && !getSurface(id)) {
      processMessages(parsed);
    }
  }, [parsed, id, getSurface, processMessages]);

  const rendererError = useA2UIError();
  return { hasError: parsed.length === 0 || rendererError !== null };
};
