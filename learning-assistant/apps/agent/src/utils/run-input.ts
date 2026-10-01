import type { BaseMessage } from "@langchain/core/messages";
import type { LearningState } from "@repo/shared/schemas";
import { readLearningState } from "@repo/shared/utils/learning-state";

import { A2UI_ACTION_TOOL, FRONTEND_TOOLS_INPUT_KEY } from "../constants/graph";
import { applyClientEdits } from "./client-edits";

/** A message as the AG-UI adapter hands it over: a plain LangChain-style object. */
interface IncomingMessage {
  id?: string;
  type?: string;
  content?: unknown;
  tool_call_id?: string;
  tool_calls?: { id?: string; name?: string }[];
}

interface RunInputParams {
  /** The thread's checkpointed values before the run; empty for a new thread. */
  before: Record<string, unknown>;
  /** The adapter's input: the browser's new messages and state. */
  input: Record<string, unknown> | null | undefined;
}

interface RunInput {
  /** The state the run starts from, after the browser's edits. */
  state: LearningState;
  /** What is written to the graph: the new messages and the state keys that changed. */
  input: Record<string, unknown>;
}

const toMessages = (raw: unknown): IncomingMessage[] =>
  Array.isArray(raw) ? (raw as IncomingMessage[]) : [];

const isActionCall = ({ type, tool_calls: calls = [] }: IncomingMessage) =>
  type === "ai" &&
  calls.length > 0 &&
  calls.every(({ name }) => name === A2UI_ACTION_TOOL);

/**
 * The messages without the pair the A2UI middleware adds for a surface
 * action (the quiz Submit): a tool call the Supervisor never made, and a
 * result that repeats the action. The action reaches the graph in the run
 * context instead, so the thread keeps only what was said and done.
 */
export const dropActionMessages = (
  messages: IncomingMessage[],
): IncomingMessage[] => {
  const actionCallIds = new Set(
    messages
      .filter(isActionCall)
      .flatMap(({ tool_calls: calls = [] }) => calls.map(({ id }) => id)),
  );
  return messages.filter(
    (message) =>
      !isActionCall(message) &&
      !(message.type === "tool" && actionCallIds.has(message.tool_call_id)),
  );
};

/**
 * The text of the student's newest message in the run, or `null` when it
 * brought none (a Submit press, a frontend tool's result). The browser sends
 * the whole thread, so messages the checkpoint already holds are skipped.
 */
export const findUserText = (
  raw: unknown,
  checkpointed: BaseMessage[],
): string | null => {
  const saved = new Set(checkpointed.map(({ id }) => id));
  const message = toMessages(raw)
    .filter(({ id, type }) => type === "human" && !saved.has(id))
    .at(-1);
  if (typeof message?.content === "string") {
    return message.content;
  }
  if (Array.isArray(message?.content)) {
    const text = (message.content as { type?: unknown; text?: unknown }[])
      .filter(({ type, text }) => type === "text" && typeof text === "string")
      .map(({ text }) => text)
      .join(" ");
    return text || null;
  }
  return null;
};

/**
 * Builds what a run writes to the graph from what the browser sent. The
 * browser's state is never written as it is: the server's state is taken
 * from the checkpoint and changed only by the edits the browser is allowed
 * to make (`applyClientEdits`). Only the keys that end up different are
 * written.
 */
export const createRunInput = ({ before, input }: RunInputParams): RunInput => {
  const messages = dropActionMessages(toMessages(input?.messages));
  const server = readLearningState(before);
  const state = applyClientEdits(server, input);
  const changed = (Object.keys(state) as (keyof LearningState)[]).filter(
    (key) => state[key] !== server[key],
  );

  return {
    state,
    input: {
      messages,
      [FRONTEND_TOOLS_INPUT_KEY]: input?.[FRONTEND_TOOLS_INPUT_KEY],
      ...Object.fromEntries(changed.map((key) => [key, state[key]])),
    },
  };
};
