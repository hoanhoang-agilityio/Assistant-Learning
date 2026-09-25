import { useA2UIActions, useA2UIError } from "@copilotkit/a2ui-renderer";
import { useEffect, useMemo } from "react";

import { parseSurfaceOperations } from "@/features/canvas/utils/a2ui-operations";

/**
 * Sends a surface's operations to the enclosing `A2UIProvider` as they
 * grow: all of them the first time, then only the components, which the
 * renderer merges by id. Compared by value, since the state is re-read on
 * every render. Returns an error when they are rejected.
 */
export const useSurfaceDraft = (
  surfaceId: string,
  operations: readonly unknown[],
) => {
  const { processMessages, getSurface } = useA2UIActions();
  const key = JSON.stringify(operations);
  const parsed = useMemo(
    () => parseSurfaceOperations(JSON.parse(key) as unknown[], surfaceId),
    [key, surfaceId],
  );

  useEffect(() => {
    if (parsed.length === 0) {
      return;
    }
    processMessages(
      getSurface(surfaceId)
        ? parsed.filter((message) => !("createSurface" in message))
        : parsed,
    );
  }, [parsed, surfaceId, getSurface, processMessages]);

  const rendererError = useA2UIError();
  return { hasError: parsed.length === 0 || rendererError !== null };
};
