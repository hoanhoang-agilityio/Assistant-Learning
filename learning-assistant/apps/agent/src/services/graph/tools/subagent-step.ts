import { dispatchCustomEvent } from "@langchain/core/callbacks/dispatch";
import { ToolMessage } from "@langchain/core/messages";
import type { ToolRuntime } from "@langchain/core/tools";
import { Command } from "@langchain/langgraph";
import type {
  Draft,
  LearningState,
  SubagentTool,
  ToolSummaryData,
  TopicConfirmationRequired,
} from "@repo/shared/schemas";
import { readLearningState } from "@repo/shared/utils/learning-state";

import {
  SUBAGENT_CLEARS,
  SUBAGENT_STAGE,
  SUBAGENT_TASK,
} from "../../../constants/agents";
import { MANUAL_STATE_EVENT } from "../../../constants/graph";
import { TOOL_FAILURE_PREFIX } from "../../../constants/tools";
import type {
  LearningGraphStateSchema,
  RunContextSchema,
} from "../../../schemas/graph";
import type { RunSettings } from "../../../types/llm";
import { formatOpenAIError } from "../../../utils/openai-errors";
import { throttleDrafts } from "../../drafts";

/** What LangChain hands a Supervisor tool: the state, the run context, the call. */
export type SubagentToolRuntime = ToolRuntime<
  typeof LearningGraphStateSchema,
  typeof RunContextSchema
>;

/** What a step works with. */
export interface StepContext {
  /** The state when the tool was called, results of earlier tools included. */
  state: LearningState;
  /** The student's settings with their API key, for the subagent's model calls. */
  settings: RunSettings;
  /** Aborted when the student stops the run. */
  signal?: AbortSignal;
  /** Streams the subagent's output so far to the canvas. */
  reportDraft: (draft: Draft) => void;
}

/**
 * How a step ended. A success names the state keys it writes and the summary
 * for the Supervisor; a failure is a message the student can act on.
 */
export type StepOutcome<T extends SubagentTool> =
  | {
      ok: true;
      update: Partial<LearningState>;
      summary: ToolSummaryData<T>;
    }
  | { ok: false; error: string };

export const failStep = (error: string): { ok: false; error: string } => ({
  ok: false,
  error,
});

const toToolMessage = (
  tool: SubagentTool,
  toolCallId: string,
  result: unknown,
): ToolMessage =>
  new ToolMessage({
    name: tool,
    tool_call_id: toolCallId,
    content: JSON.stringify(result),
  });

/**
 * The result of a tool that did nothing and changed nothing: `research`
 * waiting for the student to confirm a new topic.
 */
export const replyWithoutRunning = (
  tool: SubagentTool,
  { toolCallId }: SubagentToolRuntime,
  result: TopicConfirmationRequired,
): Command =>
  new Command({
    update: { messages: [toToolMessage(tool, toolCallId, result)] },
  });

/**
 * Runs one subagent step as a Supervisor tool and returns what it writes.
 *
 * While it runs, the canvas follows along through state snapshots that are
 * sent but not saved: the task is marked running, then each draft the step
 * reports (at most one per `DRAFT_INTERVAL_MS`). The returned `Command` is
 * what is saved. On success: the step's own keys, the later stages it makes
 * out of date cleared, the canvas moved to its stage, and a short summary
 * for the Supervisor. On failure: `status.error` and `status.failed` (the
 * canvas offers Retry), the rest kept, and the error for the Supervisor.
 * Steps never throw for a failure; a stopped run does throw, and saves
 * nothing.
 */
export const runSubagentStep = async <T extends SubagentTool>(
  tool: T,
  runtime: SubagentToolRuntime,
  apiKey: string,
  work: (step: StepContext) => Promise<StepOutcome<T>>,
): Promise<Command> => {
  const { signal } = runtime;
  const task = SUBAGENT_TASK[tool];
  const state = readLearningState(runtime.state);
  const running: LearningState = {
    ...state,
    status: { running: task },
    draft: null,
  };

  // Snapshots are sent one after another, so a draft never overtakes the
  // state that follows it.
  let sent = Promise.resolve();
  const send = (snapshot: LearningState): Promise<void> => {
    sent = sent.then(() =>
      dispatchCustomEvent(MANUAL_STATE_EVENT, snapshot, runtime.config),
    );
    return sent;
  };
  await send(running);

  let outcome: StepOutcome<T>;
  try {
    outcome = await work({
      state,
      settings: { ...runtime.context.settings, apiKey },
      signal,
      reportDraft: throttleDrafts((draft: Draft) => {
        void send({ ...running, draft });
      }),
    });
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    console.error(`[${tool}]`, error);
    outcome = failStep(
      `${TOOL_FAILURE_PREFIX[tool]}: ${formatOpenAIError(error)}`,
    );
  }

  const update: Partial<LearningState> = outcome.ok
    ? {
        ...Object.fromEntries(SUBAGENT_CLEARS[tool].map((key) => [key, null])),
        ...outcome.update,
        stage: SUBAGENT_STAGE[tool],
        status: { running: null },
        draft: null,
      }
    : {
        status: { running: null, error: outcome.error, failed: task },
        draft: null,
      };
  // The adapter keeps showing the last snapshot it was sent until the graph
  // reports the saved state, so the last one sent is the state as saved.
  await send({ ...state, ...update });

  const result = outcome.ok
    ? { ok: true, data: outcome.summary }
    : { ok: false, error: outcome.error };
  return new Command({
    update: {
      ...update,
      messages: [toToolMessage(tool, runtime.toolCallId, result)],
    },
  });
};
