import {
  type BaseEvent,
  type Context,
  EventType,
  type Message,
  type MessagesSnapshotEvent,
  type StateSnapshotEvent,
  type TextMessageContentEvent,
  type Tool,
  type ToolCallResultEvent,
  type ToolCallStartEvent,
} from "@ag-ui/client";
import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
} from "@copilotkit/runtime/v2";
import type { BaseMessage } from "@langchain/core/messages";
import type { BaseCheckpointSaver } from "@langchain/langgraph";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";
import { v4 as uuidv4 } from "uuid";

import { createLearningAgent } from "../learning-agent";
import { LearningThreadRunner } from "../thread-runner";

const BASE_PATH = "/api/copilotkit";

interface HandlerOptions {
  checkpointer: BaseCheckpointSaver;
  apiKey?: string;
  userId?: string;
}

/** One request to the run or connect endpoint, as the browser sends it. */
export interface TurnInput {
  threadId: string;
  messages?: Message[];
  state?: Record<string, unknown>;
  tools?: Tool[];
  context?: Context[];
  forwardedProps?: Record<string, unknown>;
  headers?: Record<string, string>;
}

/** The runtime handler, built the way the Next route builds it. */
export const createHandler = ({
  checkpointer,
  apiKey = "sk-test",
  userId = "user_1",
}: HandlerOptions) => {
  const runtime = new CopilotRuntime({
    agents: () => ({
      [LEARNING_AGENT_ID]: createLearningAgent({
        apiKey,
        userId,
        checkpointer,
      }),
    }),
    a2ui: { agents: [LEARNING_AGENT_ID], injectA2UITool: false },
    forwardHeaders: { deny: ["authorization"], denyPrefixes: ["x-"] },
    runner: new LearningThreadRunner(checkpointer),
  });
  return createCopilotRuntimeHandler({ runtime, basePath: BASE_PATH });
};

export type Handler = ReturnType<typeof createHandler>;

const post = async (
  handler: Handler,
  endpoint: "run" | "connect",
  turn: TurnInput,
): Promise<BaseEvent[]> => {
  const response = await handler(
    new Request(
      `http://localhost${BASE_PATH}/agent/${LEARNING_AGENT_ID}/${endpoint}`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          accept: "text/event-stream",
          ...turn.headers,
        },
        body: JSON.stringify({
          threadId: turn.threadId,
          runId: uuidv4(),
          state: turn.state ?? {},
          messages: turn.messages ?? [],
          tools: turn.tools ?? [],
          context: turn.context ?? [],
          forwardedProps: turn.forwardedProps ?? {},
        }),
      },
    ),
  );
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }
  return (await response.text())
    .split("\n")
    .filter((line) => line.startsWith("data: "))
    .map((line) => JSON.parse(line.slice("data: ".length)) as BaseEvent);
};

/** Runs one turn and returns every event the browser would receive. */
export const runTurn = (
  handler: Handler,
  turn: TurnInput,
): Promise<BaseEvent[]> => post(handler, "run", turn);

/** Reloads a thread and returns every event the browser would receive. */
export const connect = (
  handler: Handler,
  threadId: string,
): Promise<BaseEvent[]> => post(handler, "connect", { threadId });

/** Presses Stop for the thread's running run. */
export const stop = async (
  handler: Handler,
  threadId: string,
): Promise<void> => {
  await handler(
    new Request(
      `http://localhost${BASE_PATH}/agent/${LEARNING_AGENT_ID}/stop/${threadId}`,
      { method: "POST" },
    ),
  );
};

export const userMessage = (content: string): Message => ({
  id: uuidv4(),
  role: "user",
  content,
});

export const typesOf = (events: BaseEvent[]): EventType[] =>
  events.map(({ type }) => type);

/** The assistant text the run streamed to the chat. */
export const textOf = (events: BaseEvent[]): string =>
  events
    .filter(({ type }) => type === EventType.TEXT_MESSAGE_CONTENT)
    .map((event) => (event as TextMessageContentEvent).delta)
    .join("");

/** Every state snapshot of the run, in order. */
export const snapshotsOf = (events: BaseEvent[]): Record<string, unknown>[] =>
  events
    .filter(({ type }) => type === EventType.STATE_SNAPSHOT)
    .map(
      (event) =>
        (event as StateSnapshotEvent).snapshot as Record<string, unknown>,
    );

/** The state the browser holds when the run ends. */
export const lastSnapshot = (events: BaseEvent[]): Record<string, unknown> =>
  snapshotsOf(events).at(-1) ?? {};

/** The messages the browser holds when the run ends. */
export const lastMessages = (events: BaseEvent[]): Message[] =>
  events
    .filter(({ type }) => type === EventType.MESSAGES_SNAPSHOT)
    .map((event) => (event as MessagesSnapshotEvent).messages)
    .at(-1) ?? [];

/** The names of the tools the run called, in order. */
export const toolCallsOf = (events: BaseEvent[]): string[] =>
  events
    .filter(({ type }) => type === EventType.TOOL_CALL_START)
    .map((event) => (event as ToolCallStartEvent).toolCallName);

/** Every tool result of the run, parsed. */
export const toolResultsOf = (events: BaseEvent[]): unknown[] =>
  events
    .filter(({ type }) => type === EventType.TOOL_CALL_RESULT)
    .map((event): unknown =>
      JSON.parse((event as ToolCallResultEvent).content),
    );

/** What a thread's checkpoint holds, or `undefined` without one. */
export const readCheckpoint = async (
  checkpointer: BaseCheckpointSaver,
  threadId: string,
) => {
  const tuple = await checkpointer.getTuple({
    configurable: { thread_id: threadId },
  });
  return tuple?.checkpoint.channel_values as
    (Record<string, unknown> & { messages: BaseMessage[] }) | undefined;
};
