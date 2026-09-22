import { useA2UIActions, useA2UIError } from "@copilotkit/a2ui-renderer";
import { FEEDBACK_SURFACE_ID } from "@repo/shared/a2ui/feedback-catalog";
import { useEffect } from "react";

import type { A2UIMessage } from "@/features/canvas/types/a2ui";

/**
 * Sends the Evaluator's operations to the enclosing `A2UIProvider` once. The
 * provider is keyed by the operations, so new feedback gets a fresh one.
 * Returns the renderer's error, if any.
 */
export const useFeedbackSurface = (operations: readonly A2UIMessage[]) => {
  const { processMessages, getSurface } = useA2UIActions();

  // Guarded because Strict Mode runs effects twice and a surface can only be
  // created once.
  useEffect(() => {
    if (!getSurface(FEEDBACK_SURFACE_ID)) {
      processMessages([...operations]);
    }
  }, [operations, getSurface, processMessages]);

  return { error: useA2UIError() };
};
