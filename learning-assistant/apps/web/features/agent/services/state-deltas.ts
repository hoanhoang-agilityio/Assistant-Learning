import { assembleOps } from "@ag-ui/a2ui-toolkit";
import {
  BOARD_CATALOG_ID,
  BOARD_SURFACE_ID_PREFIX,
  MAX_BOARD_SURFACES,
} from "@repo/shared/a2ui/board-catalog";
import { RENDER_SURFACE_TOOL } from "@repo/shared/constants/agents";
import {
  BoardRemovalResultSchema,
  BoardSurfaceResultSchema,
  type Draft,
  type LearningState,
  type Material,
  type RunningTask,
  SUBAGENT_TOOLS,
  type SubagentTool,
  SurfaceComponentSchema,
  type ToolResult,
  type ToolResultData,
  ToolResultSchemas,
} from "@repo/shared/schemas";

import {
  SUBAGENT_CLEARS,
  SUBAGENT_STAGE,
  SUBAGENT_TASK,
} from "@/features/agent/constants/agents";
import type {
  BoardDraftEvent,
  StatePatchOperation,
  StateUpdate,
} from "@/features/agent/types/agents";
import { toDraftComponents } from "@/features/agent/utils/surface-draft";
import { getActiveMaterial, hasQuizData } from "@/utils/learning-state";

export const isSubagentTool = (name: string): name is SubagentTool =>
  (SUBAGENT_TOOLS as readonly string[]).includes(name);

/** One `add` per top-level key whose value changed. */
const createStatePatch = (
  prev: LearningState,
  next: LearningState,
): StatePatchOperation[] =>
  (Object.keys(next) as (keyof LearningState)[])
    .filter((key) => prev[key] !== next[key])
    .map((key) => ({ op: "add", path: `/${key}`, value: next[key] }));

const createStateUpdate = (
  prev: LearningState,
  next: LearningState,
): StateUpdate => ({
  state: next,
  patch: createStatePatch(prev, next),
});

const createFailureUpdate = (
  state: LearningState,
  failed: RunningTask,
  error: string,
): StateUpdate =>
  createStateUpdate(state, {
    ...state,
    status: { running: null, error, failed },
    draft: null,
  });

const clearLaterStages = (
  state: LearningState,
  tool: SubagentTool,
): LearningState => ({
  ...state,
  ...Object.fromEntries(SUBAGENT_CLEARS[tool].map((key) => [key, null])),
});

/** Replaces the selection in the active view with its simplified rewrite. */
const replaceSelection = (
  material: Material,
  selection: string,
  markdown: string,
): Material | null => {
  const text = getActiveMaterial(material);
  if (!text.includes(selection)) {
    return null;
  }
  const rewritten = text.replace(selection, () => markdown);
  return material.view === "simplified" && material.simplified !== null
    ? { ...material, simplified: rewritten }
    : { ...material, original: rewritten };
};

/**
 * Writes each tool's successful result into state, or returns an error
 * message when the result cannot be applied.
 */
const appliers: {
  [T in SubagentTool]: (
    state: LearningState,
    data: ToolResultData<T>,
    prev: LearningState,
  ) => LearningState | string;
} = {
  research: (state, { topic, research }) => ({
    ...state,
    topic,
    research,
    quizOutdated: false,
  }),

  makeMaterial: (state, { markdown }) => ({
    ...state,
    material: { original: markdown, simplified: null, view: "original" },
    quizOutdated: false,
  }),

  // Simplifying changes the learning material, so an existing quiz is out of date.
  simplify: (state, result, prev) => {
    if (!state.material) {
      return "There is no learning material to simplify.";
    }
    const quizOutdated = prev.quizOutdated || hasQuizData(prev);
    if (result.scope === "all") {
      return {
        ...state,
        material: {
          ...state.material,
          simplified: result.markdown,
          view: "simplified",
        },
        quizOutdated,
      };
    }
    const material = replaceSelection(
      state.material,
      result.selection,
      result.markdown,
    );
    return material
      ? { ...state, material, quizOutdated }
      : "The selected text is no longer in the learning material.";
  },

  generateQuiz: (state, { quiz }) => ({ ...state, quiz, quizOutdated: false }),

  evaluate: (state, { answers, evaluation, score, feedback }) =>
    state.quiz
      ? {
          ...state,
          evaluation,
          score,
          feedback,
          quiz: { ...state.quiz, answers, submitted: true },
        }
      : "There is no quiz to grade.",
};

const parseResult = <T extends SubagentTool>(
  tool: T,
  raw: unknown,
): ToolResult<T> | null => {
  const parsed = ToolResultSchemas[tool].safeParse(raw);
  return parsed.success ? (parsed.data as ToolResult<T>) : null;
};

const applyData = <T extends SubagentTool>(
  state: LearningState,
  tool: T,
  data: ToolResultData<T>,
  prev: LearningState,
): LearningState | string => appliers[tool](state, data, prev);

/** A subagent tool started: mark its task as running. */
export const createStartUpdate = (
  state: LearningState,
  tool: SubagentTool,
): StateUpdate =>
  createStateUpdate(state, {
    ...state,
    status: { running: SUBAGENT_TASK[tool] },
    draft: null,
  });

/**
 * A subagent tool returned. `content` is the `TOOL_CALL_RESULT` content (the
 * JSON-serialised tool result). On success the data is written to state, later
 * stages are cleared and the canvas moves to the tool's stage; on failure
 * `status.error` and `status.failed` are set and the rest of the state is
 * kept.
 */
export const applyToolResult = (
  state: LearningState,
  tool: SubagentTool,
  content: string,
): StateUpdate => {
  const task = SUBAGENT_TASK[tool];
  let raw: unknown;
  try {
    raw = JSON.parse(content);
  } catch {
    return createFailureUpdate(
      state,
      task,
      `The ${tool} step returned an unreadable result.`,
    );
  }

  const result = parseResult(tool, raw);
  if (!result) {
    return createFailureUpdate(
      state,
      task,
      `The ${tool} step returned an invalid result.`,
    );
  }
  if (!result.ok) {
    return createFailureUpdate(state, task, result.error);
  }

  const next = applyData(
    clearLaterStages(state, tool),
    tool,
    result.data,
    state,
  );
  if (typeof next === "string") {
    return createFailureUpdate(state, task, next);
  }

  return createStateUpdate(state, {
    ...next,
    stage: SUBAGENT_STAGE[tool],
    status: { running: null },
    draft: null,
  });
};

/**
 * A running subagent streamed more of its output. Ignored unless its task
 * is still the one running, so a late draft never outlives the result.
 */
export const applyDraft = (
  state: LearningState,
  draft: Draft,
): StateUpdate | null =>
  state.status.running === draft.task
    ? createStateUpdate(state, { ...state, draft })
    : null;

/**
 * More of a `renderSurface` (canvas) or `updateBoardSurface` call's
 * arguments arrived. The complete components so far become the Board draft:
 * a new view gets an id of its own, a revision takes the id of the view it
 * revises. `null` until there is something to draw: a root, a title, and for
 * a revision a view that exists.
 */
export const applyBoardDraft = (
  state: LearningState,
  { toolCallId, toolCallName, args }: BoardDraftEvent,
): StateUpdate | null => {
  if (typeof args !== "object" || args === null) {
    return null;
  }
  const { target, surfaceId, title, components } = args as Record<
    string,
    unknown
  >;
  const id =
    toolCallName === RENDER_SURFACE_TOOL
      ? target === "canvas"
        ? `${BOARD_SURFACE_ID_PREFIX}draft-${toolCallId}`
        : null
      : state.board.find((surface) => surface.id === surfaceId)?.id;
  const drawn = toDraftComponents(components, SurfaceComponentSchema);
  if (!id || typeof title !== "string" || title === "" || !drawn) {
    return null;
  }
  const operations = assembleOps({
    intent: "create",
    surfaceId: id,
    catalogId: BOARD_CATALOG_ID,
    components: drawn,
  });
  return createStateUpdate(state, {
    ...state,
    boardDraft: { id, title, operations },
  });
};

const parseSurfaceResult = (content: string) => {
  try {
    const parsed = BoardSurfaceResultSchema.safeParse(JSON.parse(content));
    return parsed.success ? parsed.data.surface : null;
  } catch {
    return null;
  }
};

/**
 * A `renderSurface` or `updateBoardSurface` call returned, so its draft
 * goes. A Board view is added as the newest; a revised one replaces the
 * view with its id and moves to newest, so the canvas opens on it. The
 * oldest past the limit is dropped. A chat result or an error changes
 * nothing but the draft, so this returns `null` when there was none.
 */
export const applySurfaceResult = (
  state: LearningState,
  content: string,
): StateUpdate | null => {
  const surface = parseSurfaceResult(content);
  if (!surface) {
    return state.boardDraft === null
      ? null
      : createStateUpdate(state, { ...state, boardDraft: null });
  }
  const board = [
    ...state.board.filter(({ id }) => id !== surface.id),
    surface,
  ].slice(-MAX_BOARD_SURFACES);
  return createStateUpdate(state, { ...state, board, boardDraft: null });
};

/**
 * A `deleteBoardSurface` call returned: its views leave the Board. An error
 * or unreadable content changes nothing, so this returns `null`.
 */
export const applyRemovalResult = (
  state: LearningState,
  content: string,
): StateUpdate | null => {
  let raw: unknown;
  try {
    raw = JSON.parse(content);
  } catch {
    return null;
  }
  const parsed = BoardRemovalResultSchema.safeParse(raw);
  if (!parsed.success) {
    return null;
  }
  const removed = new Set(parsed.data.removed.map(({ id }) => id));
  const board = state.board.filter(({ id }) => !removed.has(id));
  return board.length === state.board.length
    ? null
    : createStateUpdate(state, { ...state, board });
};

/**
 * The run is ending while a task is still marked running (the tool threw or
 * the run failed), or a Board view was left half-written. Clears them so the
 * canvas does not show a skeleton or a draft forever. Returns `null` when
 * nothing is left.
 */
export const interruptTask = (state: LearningState): StateUpdate | null => {
  const { running } = state.status;
  if (running === null && state.boardDraft === null) {
    return null;
  }
  const next =
    running === null
      ? state
      : createFailureUpdate(
          state,
          running,
          `The ${running} step did not finish.`,
        ).state;
  return createStateUpdate(state, { ...next, boardDraft: null });
};
