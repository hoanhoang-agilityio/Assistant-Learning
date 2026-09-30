import { v4 as uuidv4 } from "uuid";

import { Command } from "@langchain/langgraph";

/**
 * H1 candidate: a LangGraph SDK `Client` look-alike that runs a compiled
 * graph in this process, so `@ag-ui/langgraph`'s `LangGraphAgent` (all its
 * event conversion, snapshots and interrupts) works without a LangGraph
 * server. Only the 11 methods LangGraphAgent calls are implemented.
 *
 * `trusted` is what the Next route verified (Clerk userId, resolved key…);
 * it goes into the run's `context`, never from the request body.
 */
export interface InProcessOptions {
  trusted: Record<string, unknown>;
  /** Picks which top-level payload keys (spread forwardedProps) to pass on. */
  pickForwarded?: (payload: Record<string, unknown>) => Record<string, unknown>;
  onRunConfig?: (config: Record<string, unknown>) => void;
  /** State keys the client may write (run input). Default: every channel. */
  inputKeys?: string[];
  /** State keys the client may see (STATE_SNAPSHOT). Default: every channel. */
  outputKeys?: string[];
}

const snapshotToSdk = (s: any) => ({
  values: s.values ?? {},
  next: s.next ?? [],
  tasks: (s.tasks ?? []).map((t: any) => ({
    id: t.id,
    name: t.name,
    interrupts: (t.interrupts ?? []).map((i: any) => ({ value: i.value, id: i.id })),
  })),
  metadata: s.metadata ?? {},
  created_at: s.createdAt,
  checkpoint: {
    thread_id: s.config?.configurable?.thread_id,
    checkpoint_ns: s.config?.configurable?.checkpoint_ns ?? "",
    checkpoint_id: s.config?.configurable?.checkpoint_id,
  },
  parent_checkpoint: s.parentConfig
    ? { checkpoint_id: s.parentConfig.configurable?.checkpoint_id }
    : null,
});

export const createInProcessClient = (graph: any, graphId: string, opts: InProcessOptions) => {
  const running = new Map<string, AbortController>();
  const cfg = (threadId: string, checkpointId?: string) => ({
    configurable: { thread_id: threadId, ...(checkpointId ? { checkpoint_id: checkpointId } : {}) },
  });
  const channelKeys = () =>
    Object.keys(graph.channels ?? {}).filter((k) => !k.startsWith("__") && !k.includes(":"));

  return {
    assistants: {
      search: async () => [{ assistant_id: graphId, graph_id: graphId, config: {}, metadata: {} }],
      getGraph: async () => {
        const drawable = await graph.getGraphAsync();
        const json = drawable.toJSON();
        return { nodes: json.nodes.map((n: any) => ({ id: n.id })), edges: json.edges };
      },
      getSchemas: async () => {
        const props = (keys: string[]) => Object.fromEntries(keys.map((k) => [k, {}]));
        return {
          input_schema: { properties: props(opts.inputKeys ?? channelKeys()) },
          output_schema: { properties: props(opts.outputKeys ?? channelKeys()) },
          config_schema: { properties: {} },
          context_schema: { properties: {} },
        };
      },
    },
    threads: {
      get: async (threadId: string) => {
        const s = await graph.getState(cfg(threadId));
        if (!s?.config?.configurable?.checkpoint_id) throw new Error("not found");
        return { thread_id: threadId, metadata: {} };
      },
      create: async ({ threadId }: { threadId?: string }) => ({
        thread_id: threadId ?? uuidv4(),
        metadata: {},
      }),
      getState: async (threadId: string) => snapshotToSdk(await graph.getState(cfg(threadId))),
      updateState: async (
        threadId: string,
        { values, asNode, checkpointId }: { values: unknown; asNode?: string; checkpointId?: string },
      ) => {
        const next = await graph.updateState(cfg(threadId, checkpointId), values, asNode);
        return { checkpoint: { checkpoint_id: next.configurable?.checkpoint_id } };
      },
      getHistory: async (threadId: string) => {
        const out = [];
        for await (const s of graph.getStateHistory(cfg(threadId))) out.push(snapshotToSdk(s));
        return out;
      },
    },
    runs: {
      // LangGraphAgent cancels with its own AG-UI run id, which this client never sees, so cancel by thread.
      cancel: async (threadId: string, runId: string) => (running.get(runId) ?? running.get(threadId))?.abort(),
      stream: async function* (threadId: string, _assistantId: string, payload: any) {
        const { input, command, config, context, streamMode: _sm, ...forwarded } = payload;
        const runId = uuidv4();
        const abort = new AbortController();
        running.set(runId, abort);
        running.set(threadId, abort);
        const runConfig = {
          ...config,
          version: "v2" as const,
          runId,
          signal: abort.signal,
          configurable: { ...(config?.configurable ?? {}), thread_id: threadId },
          context: {
            ...(context ?? {}),
            ...(opts.pickForwarded?.(forwarded) ?? {}),
            // useAgentContext entries: the adapter puts them in input["ag-ui"], which no channel keeps
            appContext: input?.["ag-ui"]?.context ?? [],
            ...opts.trusted,
          },
        };
        opts.onRunConfig?.(runConfig);
        const graphInput = command?.resume !== undefined || command?.goto
          ? new Command(command)
          : input;
        try {
          yield { event: "metadata", data: { run_id: runId, thread_id: threadId } };
          for await (const ev of graph.streamEvents(graphInput, runConfig)) {
            yield { event: "events", data: ev };
          }
          const final = await graph.getState(cfg(threadId));
          yield { event: "values", data: final.values };
        } catch (error: any) {
          yield { event: "error", data: { message: error?.message ?? String(error) } };
        } finally {
          running.delete(runId);
          if (running.get(threadId) === abort) running.delete(threadId);
        }
      },
    },
  };
};
