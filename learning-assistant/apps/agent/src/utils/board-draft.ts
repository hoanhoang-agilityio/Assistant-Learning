import { assembleOps } from "@ag-ui/a2ui-toolkit";
import {
  BOARD_CATALOG_ID,
  BOARD_SURFACE_ID_PREFIX,
} from "@repo/shared/a2ui/board-catalog";
import { RENDER_SURFACE_TOOL } from "@repo/shared/constants/agents";
import {
  type BoardDraft,
  type BoardSurface,
  SurfaceComponentSchema,
} from "@repo/shared/schemas";

import type { SurfaceCallArgs } from "../types/graph";
import { toDraftComponents } from "./surface-draft";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * The Board draft of a `renderSurface` (canvas) or `updateBoardSurface` call
 * from its arguments so far: the complete components written yet. A new
 * view gets an id of its own, a revision takes the id of the view it
 * revises. `null` until there is something to draw: a root, a title, and
 * for a revision a view on `board`.
 */
export const toBoardDraft = (
  board: BoardSurface[],
  { toolCallId, toolCallName, args }: SurfaceCallArgs,
): BoardDraft | null => {
  if (!isRecord(args)) {
    return null;
  }
  const { target, surfaceId, title, components } = args;
  const id =
    toolCallName === RENDER_SURFACE_TOOL
      ? target === "canvas"
        ? `${BOARD_SURFACE_ID_PREFIX}draft-${toolCallId}`
        : null
      : board.find((surface) => surface.id === surfaceId)?.id;
  const drawn = toDraftComponents(components, SurfaceComponentSchema);
  if (!id || typeof title !== "string" || title === "" || !drawn) {
    return null;
  }
  return {
    id,
    title,
    operations: assembleOps({
      intent: "create",
      surfaceId: id,
      catalogId: BOARD_CATALOG_ID,
      components: drawn,
    }),
  };
};
