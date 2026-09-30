import { v4 as uuidv4 } from "uuid";

import { LangGraphAgent } from "@ag-ui/langgraph";
import { CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";
import { filter, map } from "rxjs";

import { createInProcessClient, type InProcessOptions } from "./inproc-client.ts";

export const AGENT_ID = "learning";
const BASE = "/api/copilotkit";

export interface Ev {
  type: string;
  [k: string]: any;
}

/** The runtime route as the Next handler would build it, per request. */
export const makeHandler = (
  graph: any,
  opts: InProcessOptions & { forwardHeaders?: any; dropRaw?: boolean; runner?: any },
) => {
  const build = () => {
    const agent = new LangGraphAgent({
      client: createInProcessClient(graph, AGENT_ID, opts) as any,
      graphId: AGENT_ID,
      deploymentUrl: "inproc://",
    });
    if (opts.dropRaw) {
      agent.use((input: any, next: any) => next.run(input).pipe(
          filter((e: any) => e.type !== "RAW"),
          map(({ rawEvent: _raw, ...e }: any) => e),
        ),
      );
    }
    return agent;
  };
  const runtime = new CopilotRuntime({
    agents: () => ({ [AGENT_ID]: build() }),
    a2ui: { agents: [AGENT_ID], injectA2UITool: false },
    ...(opts.forwardHeaders ? { forwardHeaders: opts.forwardHeaders } : {}),
    ...(opts.runner ? { runner: opts.runner } : {}),
  } as any);
  return createCopilotRuntimeHandler({ runtime, basePath: BASE });
};

export interface TurnInput {
  threadId: string;
  messages: any[];
  state?: Record<string, unknown>;
  forwardedProps?: Record<string, unknown>;
  headers?: Record<string, string>;
  tools?: any[];
  context?: any[];
}

export const runTurn = async (handler: any, t: TurnInput): Promise<Ev[]> => {
  const res: Response = await handler(
    new Request(`http://localhost${BASE}/agent/${AGENT_ID}/run`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "text/event-stream", ...(t.headers ?? {}) },
      body: JSON.stringify({
        threadId: t.threadId,
        runId: uuidv4(),
        state: t.state ?? {},
        messages: t.messages,
        tools: t.tools ?? [],
        context: t.context ?? [],
        forwardedProps: t.forwardedProps ?? {},
      }),
    }),
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  const text = await res.text();
  return text
    .split("\n")
    .filter((l) => l.startsWith("data: "))
    .map((l) => JSON.parse(l.slice(6)));
};

export const user = (content: string) => ({ id: uuidv4(), role: "user", content });

/** Rebuilds what the client would hold after the run: last messages snapshot and state. */
export const clientView = (events: Ev[]) => {
  const snaps = events.filter((e) => e.type === "STATE_SNAPSHOT");
  const msgs = events.filter((e) => e.type === "MESSAGES_SNAPSHOT").at(-1)?.messages ?? [];
  return { state: snaps.at(-1)?.snapshot ?? {}, messages: msgs, snapshots: snaps.map((s) => s.snapshot) };
};

export const summarize = (events: Ev[]) => {
  const counts: Record<string, number> = {};
  for (const e of events) counts[e.type] = (counts[e.type] ?? 0) + 1;
  return counts;
};

export const check = (label: string, ok: boolean, detail?: unknown) => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail === undefined ? "" : `  → ${typeof detail === "string" ? detail : JSON.stringify(detail)}`}`);
  return ok;
};
