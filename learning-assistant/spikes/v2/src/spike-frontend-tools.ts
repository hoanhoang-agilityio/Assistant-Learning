/** Frontend tools (setTheme…) through copilotkitMiddleware + LangGraphAgent, and the header deny-list. */
import "./env.ts";

import { MemorySaver } from "@langchain/langgraph";
import { v4 as uuidv4 } from "uuid";

import { buildGraph } from "./graph.ts";
import { check, clientView, makeHandler, runTurn, summarize, user } from "./harness.ts";
import { ScriptedModel } from "./scripted-model.ts";

const setTheme = {
  name: "setTheme",
  description: "Switch the app theme",
  parameters: { type: "object", properties: { theme: { type: "string", enum: ["light", "dark"] } }, required: ["theme"] },
};
const model = new ScriptedModel((m) => {
  const last = m.at(-1) as any;
  if (last._getType() === "tool") return { text: `theme result seen: ${last.content}` };
  if (String(last.content) === "dark please") return { toolCalls: [{ name: "setTheme", args: { theme: "dark" }, id: "call_theme_1" }] };
  return { text: "hi" };
});
const graph = buildGraph({ model: model as any, checkpointer: new MemorySaver(), streamResearch: async function* () {} });
let lastCfg: any;
const handler = makeHandler(graph, {
  trusted: { userId: "u1" },
  dropRaw: true,
  forwardHeaders: { deny: ["authorization"], denyPrefixes: ["x-"] },
  onRunConfig: (c) => { lastCfg = c; },
});
const threadId = uuidv4();

const e1 = await runTurn(handler, { threadId, messages: [user("dark please")], tools: [setTheme], headers: { "x-openai-key-sealed": "SEALED" } });
console.log("      turn1:", JSON.stringify(summarize(e1)));
check("frontend tool offered to the model", model.boundTools.includes("setTheme"), model.boundTools);
check("frontend tool call streamed to client", e1.some((e) => e.type === "TOOL_CALL_START" && e.toolCallName === "setTheme"));
check("server does not execute it (no TOOL_CALL_RESULT)", !e1.some((e) => e.type === "TOOL_CALL_RESULT"));
check("run ends so the client can execute it", e1.at(-1)?.type === "RUN_FINISHED");
const saved1 = (await graph.getState({ configurable: { thread_id: threadId } })).values as any;
const lastAi = saved1.messages.at(-1);
check("checkpoint keeps the ai message WITH the frontend tool call (restored after interception)", lastAi?.tool_calls?.[0]?.name === "setTheme", saved1.messages.map((m: any) => m._getType()).join(","));
check("header deny-list: no x-* headers reach the graph", !lastCfg?.configurable?.copilotkit_forwarded_headers, lastCfg?.configurable?.copilotkit_forwarded_headers);

// client executes setTheme and sends the result back (what CopilotKit does after a frontend tool)
const v1 = clientView(e1);
const toolResult = { id: uuidv4(), role: "tool", toolCallId: "call_theme_1", content: "Theme is now dark." };
const e2 = await runTurn(handler, { threadId, messages: [...v1.messages, toolResult], state: v1.state, tools: [setTheme] });
console.log("      turn2:", JSON.stringify(summarize(e2)));
const text = e2.filter((e) => e.type === "TEXT_MESSAGE_CONTENT").map((e) => e.delta).join("");
check("follow-up run: model sees the client's tool result", text.includes("Theme is now dark"), text);
const saved2 = (await graph.getState({ configurable: { thread_id: threadId } })).values as any;
check("history is well-formed (ai tool_call → tool → ai)", saved2.messages.map((m: any) => m._getType()).join(",") === "human,ai,tool,ai", saved2.messages.map((m: any) => m._getType()).join(","));
