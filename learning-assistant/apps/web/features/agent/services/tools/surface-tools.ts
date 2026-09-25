import { randomUUID } from "node:crypto";

import {
  A2UI_OPERATIONS_KEY,
  assembleOps,
  formatValidationErrors,
  validateA2UIComponents,
} from "@ag-ui/a2ui-toolkit";
import { defineTool, type ToolDefinition } from "@copilotkit/runtime/v2";
import {
  BOARD_CATALOG,
  BOARD_CATALOG_ID,
  BOARD_SURFACE_ID_PREFIX,
} from "@repo/shared/a2ui/board-catalog";
import {
  CHAT_CATALOG,
  CHAT_CATALOG_ID,
  CHAT_SURFACE_ID_PREFIX,
} from "@repo/shared/a2ui/chat-catalog";
import {
  DELETE_BOARD_SURFACE_TOOL,
  READ_BOARD_SURFACE_TOOL,
  RENDER_SURFACE_TOOL,
  UPDATE_BOARD_SURFACE_TOOL,
} from "@repo/shared/constants/agents";
import {
  type BoardRemovalResult,
  type BoardSurface,
  DeleteBoardSurfaceArgsSchema,
  ReadBoardSurfaceArgsSchema,
  RenderSurfaceArgsSchema,
  type SurfaceComponent,
  type SurfaceTarget,
  UpdateBoardSurfaceArgsSchema,
} from "@repo/shared/schemas";

import {
  BOARD_EMPTY,
  BOARD_SURFACE_NOT_FOUND,
  DELETE_BOARD_SURFACE_TOOL_DESCRIPTION,
  NO_SURFACE_IDS,
  READ_BOARD_SURFACE_TOOL_DESCRIPTION,
  RENDER_SURFACE_TOOL_DESCRIPTION,
  SURFACE_ERROR_PREFIX,
  UPDATE_BOARD_SURFACE_TOOL_DESCRIPTION,
} from "@/features/agent/constants/tools";
import type { SupervisorRunContext } from "@/features/agent/types/agents";
import { getSurfaceComponents } from "@/features/agent/utils/board-surface";

/** Each target's catalog, and the prefix of the ids the server gives it. */
const TARGETS = {
  chat: {
    catalog: CHAT_CATALOG,
    catalogId: CHAT_CATALOG_ID,
    idPrefix: CHAT_SURFACE_ID_PREFIX,
  },
  canvas: {
    catalog: BOARD_CATALOG,
    catalogId: BOARD_CATALOG_ID,
    idPrefix: BOARD_SURFACE_ID_PREFIX,
  },
} as const satisfies Record<SurfaceTarget, unknown>;

/** The validation errors for the model to fix, or `null` for a valid tree. */
const findTreeErrors = (
  target: SurfaceTarget,
  components: SurfaceComponent[],
): string | null => {
  const { valid, errors } = validateA2UIComponents({
    components,
    catalog: TARGETS[target].catalog,
    validateBindings: false,
  });
  return valid
    ? null
    : `${SURFACE_ERROR_PREFIX}\n${formatValidationErrors(errors)}`;
};

/**
 * A Board view's operations. Always a full create, never an A2UI `update`:
 * the state keeps one list per view, and the client redraws a revised view
 * from scratch.
 */
const createBoardOperations = (
  surfaceId: string,
  components: SurfaceComponent[],
) =>
  assembleOps({
    intent: "create",
    surfaceId,
    catalogId: BOARD_CATALOG_ID,
    components,
  });

/** Why a Board view id matched nothing, with the ids that would. */
const describeMissing = (board: BoardSurface[]): string =>
  board.length === 0
    ? BOARD_EMPTY
    : `${BOARD_SURFACE_NOT_FOUND} ${board
        .map(({ id, title }) => `${id} ("${title}")`)
        .join(", ")}.`;

/** The Board view with `surfaceId`, or the error the model reads instead. */
const findBoardSurface = (
  board: BoardSurface[],
  surfaceId: string,
): BoardSurface | { error: string } =>
  board.find(({ id }) => id === surfaceId) ?? { error: describeMissing(board) };

/**
 * Dynamic A2UI, in the chat or on the canvas Board. The Supervisor composes
 * the tree itself; the schema limits it to Board components and the toolkit
 * checks it against the target's catalog (one root, every child resolved,
 * no cycles, chat-only components in the chat). Surface ids are the app's,
 * never the model's; an invalid tree returns the errors so it can be fixed.
 *
 * - `renderSurface` (chat) returns an `a2ui_operations` envelope, which the
 *   A2UI middleware turns into an activity the chat draws.
 * - `renderSurface` (canvas) and `updateBoardSurface` return `{ surface }`,
 *   which `syncStateFromTools` writes to `state.board`. There is no
 *   envelope, so the middleware leaves them out of the chat.
 * - `readBoardSurface` returns a view's components, since the Supervisor's
 *   state only lists Board views by id and title.
 * - `deleteBoardSurface` returns `{ removed }`, which `syncStateFromTools`
 *   takes off `state.board`. Ids that match nothing are ignored when others
 *   match.
 */
export const createSurfaceTools = ({
  getState,
}: SupervisorRunContext): ToolDefinition[] => [
  defineTool({
    name: RENDER_SURFACE_TOOL,
    description: RENDER_SURFACE_TOOL_DESCRIPTION,
    parameters: RenderSurfaceArgsSchema,
    execute: async ({ target, title, components }) => {
      const error = findTreeErrors(target, components);
      if (error) {
        return { error };
      }

      const surfaceId = `${TARGETS[target].idPrefix}${randomUUID()}`;
      if (target === "chat") {
        return {
          [A2UI_OPERATIONS_KEY]: assembleOps({
            intent: "create",
            surfaceId,
            catalogId: CHAT_CATALOG_ID,
            components,
          }),
        };
      }
      const surface: BoardSurface = {
        id: surfaceId,
        title,
        operations: createBoardOperations(surfaceId, components),
        revision: 1,
      };
      return { surface };
    },
  }),

  defineTool({
    name: READ_BOARD_SURFACE_TOOL,
    description: READ_BOARD_SURFACE_TOOL_DESCRIPTION,
    parameters: ReadBoardSurfaceArgsSchema,
    execute: async ({ surfaceId }) => {
      const found = findBoardSurface(getState().board, surfaceId);
      if ("error" in found) {
        return found;
      }
      return {
        surfaceId: found.id,
        title: found.title,
        components: getSurfaceComponents(found) ?? [],
      };
    },
  }),

  defineTool({
    name: DELETE_BOARD_SURFACE_TOOL,
    description: DELETE_BOARD_SURFACE_TOOL_DESCRIPTION,
    parameters: DeleteBoardSurfaceArgsSchema,
    execute: async ({
      surfaceIds,
    }): Promise<BoardRemovalResult | { error: string }> => {
      if (surfaceIds.length === 0) {
        return { error: NO_SURFACE_IDS };
      }
      const { board } = getState();
      const ids = new Set(surfaceIds);
      const removed = board
        .filter(({ id }) => ids.has(id))
        .map(({ id, title }) => ({ id, title }));
      // Nothing matched: remove nothing and say which ids exist.
      return removed.length > 0
        ? { removed }
        : { error: describeMissing(board) };
    },
  }),

  defineTool({
    name: UPDATE_BOARD_SURFACE_TOOL,
    description: UPDATE_BOARD_SURFACE_TOOL_DESCRIPTION,
    parameters: UpdateBoardSurfaceArgsSchema,
    execute: async ({ surfaceId, title, components }) => {
      const found = findBoardSurface(getState().board, surfaceId);
      if ("error" in found) {
        return found;
      }
      const error = findTreeErrors("canvas", components);
      if (error) {
        return { error };
      }

      const surface: BoardSurface = {
        id: found.id,
        title,
        operations: createBoardOperations(found.id, components),
        revision: found.revision + 1,
      };
      return { surface };
    },
  }),
];
