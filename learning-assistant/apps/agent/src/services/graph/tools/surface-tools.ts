import {
  A2UI_OPERATIONS_KEY,
  assembleOps,
  formatValidationErrors,
  validateA2UIComponents,
} from "@ag-ui/a2ui-toolkit";
import { dispatchCustomEvent } from "@langchain/core/callbacks/dispatch";
import { ToolMessage } from "@langchain/core/messages";
import { Command } from "@langchain/langgraph";
import {
  BOARD_CATALOG,
  BOARD_CATALOG_ID,
  BOARD_SURFACE_ID_PREFIX,
  MAX_BOARD_SURFACES,
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
import { readLearningState } from "@repo/shared/utils/learning-state";
import { tool } from "langchain";
import { v4 as uuidv4 } from "uuid";

import { MANUAL_STATE_EVENT } from "../../../constants/graph";
import {
  BOARD_EMPTY,
  BOARD_SURFACE_NOT_FOUND,
  DELETE_BOARD_SURFACE_TOOL_DESCRIPTION,
  NO_SURFACE_IDS,
  READ_BOARD_SURFACE_TOOL_DESCRIPTION,
  RENDER_SURFACE_TOOL_DESCRIPTION,
  SURFACE_ERROR_PREFIX,
  UPDATE_BOARD_SURFACE_TOOL_DESCRIPTION,
} from "../../../constants/tools";
import { getSurfaceComponents } from "../../../utils/board-surface";
import type { SubagentToolRuntime } from "./subagent-step";

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

/** A tool result the Supervisor reads, and the chat card shows. */
const toResult = (result: unknown): string => JSON.stringify(result);

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
 * The Board with `surface` as its newest view: a revised view leaves its old
 * place, so the canvas opens on it. The oldest past the limit is dropped.
 */
const addToBoard = (
  board: BoardSurface[],
  surface: BoardSurface,
): BoardSurface[] =>
  [...board.filter(({ id }) => id !== surface.id), surface].slice(
    -MAX_BOARD_SURFACES,
  );

/**
 * Saves a new Board and tells the Supervisor which view changed. The state
 * as saved is sent first: the adapter shows it until the graph reports the
 * saved state, so the Board draft and the view never show together.
 */
const writeBoard = async (
  name: string,
  runtime: SubagentToolRuntime,
  board: BoardSurface[],
  result: unknown,
): Promise<Command> => {
  const update = { board, boardDraft: null };
  await dispatchCustomEvent(
    MANUAL_STATE_EVENT,
    { ...readLearningState(runtime.state), ...update },
    runtime.config,
  );
  return new Command({
    update: {
      ...update,
      messages: [
        new ToolMessage({
          name,
          tool_call_id: runtime.toolCallId,
          content: toResult(result),
        }),
      ],
    },
  });
};

/** A Board view's result: the view itself goes to state. */
const toSurfaceResult = ({ id, title, revision }: BoardSurface) => ({
  surface: { id, title, revision },
});

/**
 * Dynamic A2UI, in the chat or on the canvas Board. The Supervisor composes
 * the tree itself; the schema limits it to Board components and the toolkit
 * checks it against the target's catalog (one root, every child resolved,
 * no cycles, chat-only components in the chat). Surface ids are the app's,
 * never the model's; an invalid tree returns the errors so it can be fixed.
 *
 * - `renderSurface` (chat) returns an `a2ui_operations` envelope, which the
 *   A2UI middleware turns into a surface the chat draws.
 * - `renderSurface` (canvas) and `updateBoardSurface` write the view to
 *   `state.board` and return which view it was.
 * - `readBoardSurface` returns a view's components, since the Supervisor's
 *   state only lists Board views by id and title.
 * - `deleteBoardSurface` takes views off `state.board` and returns them.
 *   Ids that match nothing are ignored when others match.
 */
export const createSurfaceTools = () => [
  tool(
    async (
      { target, title, components },
      runtime: SubagentToolRuntime,
    ): Promise<string | Command> => {
      const error = findTreeErrors(target, components);
      if (error) {
        return toResult({ error });
      }

      const surfaceId = `${TARGETS[target].idPrefix}${uuidv4()}`;
      if (target === "chat") {
        return toResult({
          [A2UI_OPERATIONS_KEY]: assembleOps({
            intent: "create",
            surfaceId,
            catalogId: CHAT_CATALOG_ID,
            components,
          }),
        });
      }
      const surface: BoardSurface = {
        id: surfaceId,
        title,
        operations: createBoardOperations(surfaceId, components),
        revision: 1,
      };
      const { board } = readLearningState(runtime.state);
      return writeBoard(
        RENDER_SURFACE_TOOL,
        runtime,
        addToBoard(board, surface),
        toSurfaceResult(surface),
      );
    },
    {
      name: RENDER_SURFACE_TOOL,
      description: RENDER_SURFACE_TOOL_DESCRIPTION,
      schema: RenderSurfaceArgsSchema,
    },
  ),

  tool(
    ({ surfaceId }, runtime: SubagentToolRuntime): string => {
      const found = findBoardSurface(
        readLearningState(runtime.state).board,
        surfaceId,
      );
      if ("error" in found) {
        return toResult(found);
      }
      return toResult({
        surfaceId: found.id,
        title: found.title,
        components: getSurfaceComponents(found) ?? [],
      });
    },
    {
      name: READ_BOARD_SURFACE_TOOL,
      description: READ_BOARD_SURFACE_TOOL_DESCRIPTION,
      schema: ReadBoardSurfaceArgsSchema,
    },
  ),

  tool(
    async (
      { surfaceId, title, components },
      runtime: SubagentToolRuntime,
    ): Promise<string | Command> => {
      const { board } = readLearningState(runtime.state);
      const found = findBoardSurface(board, surfaceId);
      if ("error" in found) {
        return toResult(found);
      }
      const error = findTreeErrors("canvas", components);
      if (error) {
        return toResult({ error });
      }

      const surface: BoardSurface = {
        id: found.id,
        title,
        operations: createBoardOperations(found.id, components),
        revision: found.revision + 1,
      };
      return writeBoard(
        UPDATE_BOARD_SURFACE_TOOL,
        runtime,
        addToBoard(board, surface),
        toSurfaceResult(surface),
      );
    },
    {
      name: UPDATE_BOARD_SURFACE_TOOL,
      description: UPDATE_BOARD_SURFACE_TOOL_DESCRIPTION,
      schema: UpdateBoardSurfaceArgsSchema,
    },
  ),

  tool(
    async (
      { surfaceIds },
      runtime: SubagentToolRuntime,
    ): Promise<string | Command> => {
      if (surfaceIds.length === 0) {
        return toResult({ error: NO_SURFACE_IDS });
      }
      const { board } = readLearningState(runtime.state);
      const ids = new Set(surfaceIds);
      const removed = board
        .filter(({ id }) => ids.has(id))
        .map(({ id, title }) => ({ id, title }));
      // Nothing matched: remove nothing and say which ids exist.
      if (removed.length === 0) {
        return toResult({ error: describeMissing(board) });
      }
      const result: BoardRemovalResult = { removed };
      return writeBoard(
        DELETE_BOARD_SURFACE_TOOL,
        runtime,
        board.filter(({ id }) => !ids.has(id)),
        result,
      );
    },
    {
      name: DELETE_BOARD_SURFACE_TOOL,
      description: DELETE_BOARD_SURFACE_TOOL_DESCRIPTION,
      schema: DeleteBoardSurfaceArgsSchema,
    },
  ),
];
