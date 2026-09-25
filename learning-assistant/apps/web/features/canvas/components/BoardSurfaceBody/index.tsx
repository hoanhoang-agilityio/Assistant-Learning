import { A2UIRenderer } from "@copilotkit/a2ui-renderer";
import type { BoardSurface } from "@repo/shared/schemas";

import { StageError } from "@/features/canvas/components/StageError";
import { SurfaceBoundary } from "@/features/canvas/components/SurfaceBoundary";
import { BOARD_SURFACE_ERROR } from "@/features/canvas/constants/a2ui";
import { useBoardSurface } from "@/features/canvas/hooks/use-board-surface";

export interface BoardSurfaceBodyProps {
  surface: BoardSurface;
}

/** Draws one Board view, or an error if it cannot be drawn. */
export const BoardSurfaceBody = ({ surface }: BoardSurfaceBodyProps) => {
  const { hasError } = useBoardSurface(surface);
  const fallback = <StageError message={BOARD_SURFACE_ERROR} />;

  return hasError ? (
    fallback
  ) : (
    <SurfaceBoundary fallback={fallback}>
      <A2UIRenderer surfaceId={surface.id} />
    </SurfaceBoundary>
  );
};
