import { A2UIRenderer } from "@copilotkit/a2ui-renderer";
import type { ReactNode } from "react";

import { SurfaceBoundary } from "@/features/canvas/components/SurfaceBoundary";
import { useSurfaceDraft } from "@/features/canvas/hooks/use-surface-draft";

export interface SurfaceDraftBodyProps {
  surfaceId: string;
  /** The surface's operations so far. */
  operations: readonly unknown[];
  /** Shown while the draft cannot be drawn; the finished surface replaces it. */
  fallback?: ReactNode;
}

/** Draws a dynamic surface that is still being written, as it grows. */
export const SurfaceDraftBody = ({
  surfaceId,
  operations,
  fallback = null,
}: SurfaceDraftBodyProps) => {
  const { hasError } = useSurfaceDraft(surfaceId, operations);

  return hasError ? (
    fallback
  ) : (
    <SurfaceBoundary fallback={fallback}>
      <A2UIRenderer surfaceId={surfaceId} />
    </SurfaceBoundary>
  );
};
