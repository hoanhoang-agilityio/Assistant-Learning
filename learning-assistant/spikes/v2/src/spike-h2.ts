/** S1/H2: CopilotRuntime → LangGraphAgent(deploymentUrl) → LangGraph dev server (spikes/v2-h2). */
import "./env.ts";

import { LangGraphAgent } from "@ag-ui/langgraph";
import { CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";
import { v4 as uuidv4 } from "uuid";

import { AGENT_ID, check, clientView, runTurn, summarize, user } from "./harness.ts";

const runtime = new CopilotRuntime({
  agents: () => ({
    [AGENT_ID]: new LangGraphAgent({
      deploymentUrl: "http://localhost:2024",
      graphId: "learning",
      // the only documented way to hand the server a trusted value
      assistantConfig: { configurable: { userId: "user_from_next" } } as any,
    }),
  }),
  a2ui: { agents: [AGENT_ID], injectA2UITool: false },
} as any);
const handler = createCopilotRuntimeHandler({ runtime, basePath: "/api/copilotkit" });

const threadId = uuidv4();
const t0 = Date.now();
const e1 = await runTurn(handler, { threadId, messages: [user("research tides")] });
console.log("turn1:", JSON.stringify(summarize(e1)), `${Date.now() - t0}ms`);
const v1 = clientView(e1);
check("H2 run finishes", e1.at(-1)?.type === "RUN_FINISHED", e1.find((e) => e.type === "RUN_ERROR")?.message);
check("H2 drafts via manually_emit_state reach client", v1.snapshots.some((s: any) => s.draft?.task === "research"));
check("H2 final state", v1.state.research?.title === "Tides", Object.keys(v1.state));

const e2 = await runTurn(handler, {
  threadId,
  messages: [...v1.messages, user("whoami")],
  state: v1.state,
  forwardedProps: { settings: { level: "beginner" }, config: { configurable: { userId: "FORGED_BY_CLIENT" } } },
  headers: { "x-openai-key-sealed": "SEALED", "x-user-id": "FORGED_HEADER" },
});
const who = e2.find((e) => e.type === "TOOL_CALL_RESULT")?.content;
console.log("      whoami on H2:", who ?? e2.find((e) => e.type === "RUN_ERROR")?.message);
check("H2 forwardedProps.settings does NOT reach the graph", !String(who).includes("beginner"));
check("H2 client can forge configurable via forwardedProps.config", String(who).includes("FORGED_BY_CLIENT"));
check("H2 client x-* headers reach graph config", String(who).includes("FORGED_HEADER"));

// reload in H2: connect
const res = await handler(new Request(`http://localhost/api/copilotkit/agent/${AGENT_ID}/connect`, {
  method: "POST", headers: { "content-type": "application/json" },
  body: JSON.stringify({ threadId, runId: uuidv4(), state: {}, messages: [], tools: [], context: [], forwardedProps: {} }),
}));
console.log(`      H2 /connect (same process, so in-memory replay): ${(await res.text()).split("\n").filter((l) => l.startsWith("data: ")).length} events`);
