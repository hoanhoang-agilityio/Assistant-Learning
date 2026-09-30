/** S2 follow-up: what does copilotkitMiddleware do with useAgentContext entries? */
import "./env.ts";

import { MemorySaver } from "@langchain/langgraph";
import { v4 as uuidv4 } from "uuid";

import { buildGraph } from "./graph.ts";
import { check, clientView, makeHandler, runTurn, user } from "./harness.ts";
import { ScriptedModel } from "./scripted-model.ts";

const model = new ScriptedModel(() => ({ text: "ok" }));
const graph = buildGraph({ model: model as any, checkpointer: new MemorySaver(), streamResearch: async function* () {} });
let lastCtx: any;
const handler = makeHandler(graph, { trusted: { userId: "u1" }, dropRaw: true, onRunConfig: (c: any) => { lastCtx = c.context; } });
const threadId = uuidv4();
const context = [
  { description: "What the student sees on screen", value: "layout=split theme=dark" },
  { description: "A2UI Component Schema — available components", value: "{\"catalogId\":\"x\"}" },
];
const e1 = await runTurn(handler, { threadId, messages: [user("hi")], context });
const v1 = clientView(e1);
const e2 = await runTurn(handler, { threadId, messages: [...v1.messages, user("again")], state: v1.state, context: [{ description: "What the student sees on screen", value: "layout=canvas" }] });
const saved = (await graph.getState({ configurable: { thread_id: threadId } })).values as any;
const seenText = JSON.stringify(model.calls.map((c) => c.map((m: any) => m.content)));
check("useAgentContext entries reach the model through copilotkitMiddleware", seenText.includes("layout="), "model saw only the system prompt + chat");
check("nothing context-related is persisted into checkpoint messages", !saved.messages.some((m: any) => m._getType() === "system"));
console.log("      model saw:", model.calls.at(-1)!.map((m: any) => m._getType()).join(","));
for (const m of model.calls.at(-1)!) if ((m as any)._getType() === "system") console.log("      system seen by model:", JSON.stringify((m as any).content).slice(0, 400).replace(/\n/g, " ⏎ "));
console.log("      state['ag-ui'].context present in checkpoint:", JSON.stringify(saved["ag-ui"] ?? null).slice(0, 200));
check("in-process client can hand useAgentContext entries to the graph as run context", lastCtx?.appContext?.some((c: any) => c.value === "layout=canvas"), lastCtx?.appContext?.map((c: any) => c.description));
