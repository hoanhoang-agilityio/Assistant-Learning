import {
  type LearningState,
  type Notes,
  SUBAGENT_TOOLS,
  type SubagentTool,
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
  StatePatchOperation,
  StateUpdate,
} from "@/features/agent/types/agents";

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

const handleToolFail = (state: LearningState, error: string): StateUpdate =>
  createStateUpdate(state, { ...state, status: { running: null, error } });

const clearLaterStages = (
  state: LearningState,
  tool: SubagentTool,
): LearningState => ({
  ...state,
  ...Object.fromEntries(SUBAGENT_CLEARS[tool].map((key) => [key, null])),
});

const getActiveText = (notes: Notes) =>
  notes.view === "simplified" && notes.simplified !== null
    ? notes.simplified
    : notes.original;

/** Replaces the selection in the active view with its simplified rewrite. */
const replaceSelection = (
  notes: Notes,
  selection: string,
  markdown: string,
): Notes | null => {
  const text = getActiveText(notes);
  if (!text.includes(selection)) return null;
  const rewritten = text.replace(selection, () => markdown);
  return notes.view === "simplified" && notes.simplified !== null
    ? { ...notes, simplified: rewritten }
    : { ...notes, original: rewritten };
};

/**
 * Writes each tool's successful result into state, or returns an error
 * message when the result cannot be applied.
 */
const appliers: {
  [T in SubagentTool]: (
    state: LearningState,
    data: ToolResultData<T>,
  ) => LearningState | string;
} = {
  research: (state, { topic, research }) => ({ ...state, topic, research }),

  makeNotes: (state, { markdown }) => ({
    ...state,
    notes: { original: markdown, simplified: null, view: "original" },
  }),

  simplify: (state, result) => {
    if (!state.notes) return "There are no notes to simplify.";
    if (result.scope === "all") {
      return {
        ...state,
        notes: {
          ...state.notes,
          simplified: result.markdown,
          view: "simplified",
        },
      };
    }
    const notes = replaceSelection(
      state.notes,
      result.selection,
      result.markdown,
    );
    return notes
      ? { ...state, notes }
      : "The selected text is no longer in the notes.";
  },

  generateQuiz: (state, { quiz }) => ({ ...state, quiz }),

  evaluate: (state, { evaluation, score, feedback }) => ({
    ...state,
    evaluation,
    score,
    feedback,
    quiz: state.quiz && { ...state.quiz, submitted: true },
  }),
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
): LearningState | string => appliers[tool](state, data);

/** A subagent tool started: mark its task as running. */
export const handleStartTask = (
  state: LearningState,
  tool: SubagentTool,
): StateUpdate =>
  createStateUpdate(state, {
    ...state,
    status: { running: SUBAGENT_TASK[tool] },
  });

/**
 * A subagent tool returned. `content` is the `TOOL_CALL_RESULT` content (the
 * JSON-serialised tool result). On success the data is written to state, later
 * stages are cleared and the canvas moves to the tool's stage; on handleToolFailure
 * `status.error` is set and the rest of the state is kept.
 */
export const applyToolResult = (
  state: LearningState,
  tool: SubagentTool,
  content: string,
): StateUpdate => {
  let raw: unknown;
  try {
    raw = JSON.parse(content);
  } catch {
    return handleToolFail(
      state,
      `The ${tool} step returned an unreadable result.`,
    );
  }

  const result = parseResult(tool, raw);
  if (!result) {
    return handleToolFail(
      state,
      `The ${tool} step returned an invalid result.`,
    );
  }
  if (!result.ok) return handleToolFail(state, result.error);

  const next = applyData(clearLaterStages(state, tool), tool, result.data);
  if (typeof next === "string") return handleToolFail(state, next);

  return createStateUpdate(state, {
    ...next,
    stage: SUBAGENT_STAGE[tool],
    status: { running: null },
  });
};

/**
 * The run is ending while a task is still marked running (the tool threw or
 * the run failed). Clears it so the stage does not show a skeleton forever.
 * Returns `null` when nothing is running.
 */
export const interruptTask = (state: LearningState): StateUpdate | null =>
  state.status.running === null
    ? null
    : handleToolFail(state, `The ${state.status.running} step did not finish.`);
