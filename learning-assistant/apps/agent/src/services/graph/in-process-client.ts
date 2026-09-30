import type { StateSnapshot } from "@langchain/langgraph";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";
import { v4 as uuidv4 } from "uuid";

import {
  APP_CONTEXT_INPUT_KEY,
  CLIENT_INPUT_STATE_KEYS,
  CLIENT_VISIBLE_STATE_KEYS,
  FRONTEND_TOOLS_INPUT_KEY,
  GRAPH_RECURSION_LIMIT,
} from "../../constants/graph";
import type { RunContext } from "../../schemas/graph";
import { getErrorMessage } from "../../utils/openai-errors";
import { readAppContext, readRunSettings } from "../../utils/run-context";
import { createRunInput } from "../../utils/run-input";
import { parseSubmitAction } from "../../utils/submit-action";
import type { LearningGraph } from "./learning-graph";

interface InProcessClientOptions {
  graph: LearningGraph;
  /** The signed-in user, from the verified session. Never from the request. */
  userId: string;
}

/**
 * What `LangGraphAgent` hands to `runs.stream`: the run's input state, then
 * the browser's `forwardedProps` spread at the top level.
 */
interface RunPayload {
  input?: Record<string, unknown> | null;
  /** `forwardedProps.settings`, as the browser sent it. */
  settings?: unknown;
  /** `forwardedProps.a2uiAction`: a surface action, such as the quiz Submit. */
  a2uiAction?: unknown;
}

/** A drawable graph as JSON: the adapter reads node ids and edges. */
interface GraphJson {
  nodes: { id: string }[];
  edges: unknown[];
}

/** A run's input as the graph types it; `createRunInput` builds it untyped. */
type GraphInput = Parameters<LearningGraph["graph"]["streamEvents"]>[0];

interface UpdateStateOptions {
  values: Record<string, unknown>;
  asNode?: string;
  checkpointId?: string;
}

const toThreadConfig = (threadId: string, checkpointId?: string) => ({
  configurable: {
    thread_id: threadId,
    ...(checkpointId ? { checkpoint_id: checkpointId } : {}),
  },
});

/** A schema as the adapter reads it: only the property names matter. */
const toSchema = (keys: readonly string[]) => ({
  properties: Object.fromEntries(keys.map((key) => [key, {}])),
});

/** A graph state in the shape the LangGraph SDK returns. */
const toThreadState = ({
  values,
  next,
  tasks,
  metadata,
  createdAt,
  config,
  parentConfig,
}: StateSnapshot) => ({
  values: values ?? {},
  next: next ?? [],
  tasks: (tasks ?? []).map(({ id, name, interrupts }) => ({
    id,
    name,
    interrupts: (interrupts ?? []).map(({ id, value }) => ({ id, value })),
  })),
  metadata: metadata ?? {},
  created_at: createdAt,
  checkpoint: {
    thread_id: config.configurable?.thread_id,
    checkpoint_ns: config.configurable?.checkpoint_ns ?? "",
    checkpoint_id: config.configurable?.checkpoint_id,
  },
  parent_checkpoint: parentConfig
    ? { checkpoint_id: parentConfig.configurable?.checkpoint_id }
    : null,
});

/**
 * A LangGraph SDK `Client` look-alike that runs the graph in this process,
 * so `LangGraphAgent` (its event conversion and snapshots) works without a
 * LangGraph server. Only the methods `LangGraphAgent` calls exist.
 *
 * It is also the trust boundary between the browser and the graph:
 * - The run's `context` is built here: the verified `userId`, the settings,
 *   the `useAgentContext` entries and a quiz Submit. Nothing else the
 *   browser sent (`config`, `context`, `command`, any other forwarded prop)
 *   is passed on.
 * - The run's input is built here too (`createRunInput`): the new messages,
 *   and the server's own state changed only by the edits the browser may
 *   make. The browser's state is never written as it is.
 * - The schemas it reports make the adapter cut the browser's state down
 *   before it arrives, and the snapshots down to the keys the browser may
 *   see.
 */
export const createInProcessClient = ({
  graph,
  userId,
}: InProcessClientOptions) => {
  const compiled = graph.graph;
  const running = new Map<string, AbortController>();

  return {
    assistants: {
      search: async () => [
        {
          assistant_id: LEARNING_AGENT_ID,
          graph_id: LEARNING_AGENT_ID,
          config: {},
          metadata: {},
        },
      ],
      getGraph: async () => {
        const drawable = await compiled.getGraphAsync();
        const { nodes, edges } = drawable.toJSON() as GraphJson;
        return { nodes: nodes.map(({ id }) => ({ id })), edges };
      },
      getSchemas: async () => ({
        input_schema: toSchema([
          ...CLIENT_INPUT_STATE_KEYS,
          FRONTEND_TOOLS_INPUT_KEY,
          APP_CONTEXT_INPUT_KEY,
        ]),
        output_schema: toSchema(CLIENT_VISIBLE_STATE_KEYS),
        config_schema: toSchema([]),
        context_schema: toSchema([]),
      }),
    },

    threads: {
      get: async (threadId: string) => {
        const { config } = await compiled.getState(toThreadConfig(threadId));
        if (!config.configurable?.checkpoint_id) {
          throw new Error(`Thread ${threadId} has no checkpoint`);
        }
        return { thread_id: threadId, metadata: {} };
      },
      create: async ({ threadId }: { threadId?: string } = {}) => ({
        thread_id: threadId ?? uuidv4(),
        metadata: {},
      }),
      getState: async (threadId: string) =>
        toThreadState(await compiled.getState(toThreadConfig(threadId))),
      updateState: async (
        threadId: string,
        { values, asNode, checkpointId }: UpdateStateOptions,
      ) => {
        const config = await compiled.updateState(
          toThreadConfig(threadId, checkpointId),
          values,
          asNode,
        );
        return {
          checkpoint: { checkpoint_id: config.configurable?.checkpoint_id },
        };
      },
      getHistory: async (threadId: string) => {
        const history = [];
        for await (const snapshot of compiled.getStateHistory(
          toThreadConfig(threadId),
        )) {
          history.push(toThreadState(snapshot));
        }
        return history;
      },
    },

    runs: {
      // The adapter cancels with its own AG-UI run id, which never reaches
      // this client, so a run is found by its thread.
      cancel: async (threadId: string) => {
        running.get(threadId)?.abort();
      },
      stream: async function* (
        threadId: string,
        _assistantId: string,
        { input, settings, a2uiAction }: RunPayload,
      ) {
        const runId = uuidv4();
        const abort = new AbortController();
        running.set(threadId, abort);

        const context: RunContext = {
          userId,
          settings: readRunSettings(settings),
          appContext: readAppContext(
            (input?.[APP_CONTEXT_INPUT_KEY] as { context?: unknown })?.context,
          ),
          submit: parseSubmitAction({ a2uiAction }),
        };

        try {
          yield {
            event: "metadata",
            data: { run_id: runId, thread_id: threadId },
          };
          const before = await compiled.getState(toThreadConfig(threadId));
          const run = createRunInput({ before: before.values ?? {}, input });
          // The state the run starts from. The adapter builds each snapshot
          // from the values it has seen so far; without this, the first
          // ones hold only the keys a node has just written, and the
          // canvas would go blank until the run ends.
          yield { event: "values", data: { ...before.values, ...run.state } };
          const events = compiled.streamEvents(run.input as GraphInput, {
            ...toThreadConfig(threadId),
            version: "v2",
            streamMode: "values",
            recursionLimit: GRAPH_RECURSION_LIMIT,
            runId,
            runName: LEARNING_AGENT_ID,
            signal: abort.signal,
            context,
          });
          for await (const event of events) {
            // The graph's own stream: the whole state after each step.
            if (event.event === "on_chain_stream" && event.run_id === runId) {
              yield { event: "values", data: event.data.chunk };
            }
            yield { event: "events", data: event };
          }
          const { values } = await compiled.getState(toThreadConfig(threadId));
          yield { event: "values", data: values };
        } catch (error) {
          // A stopped run ends quietly: the adapter then sends what was saved.
          if (!abort.signal.aborted) {
            yield { event: "error", data: { message: getErrorMessage(error) } };
          }
        } finally {
          // Also reached when the adapter stops reading: end the graph too.
          abort.abort();
          if (running.get(threadId) === abort) {
            running.delete(threadId);
          }
        }
      },
    },
  };
};
