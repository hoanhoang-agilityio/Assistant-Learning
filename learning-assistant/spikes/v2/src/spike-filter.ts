/**
 * S4 follow-up: can the route keep server-only state out of the browser and
 * stop the client overwriting server-owned keys? input/output schema keys +
 * a RAW-dropping AG-UI middleware.
 */
import "./env.ts";

import { MemorySaver } from "@langchain/langgraph";
import { v4 as uuidv4 } from "uuid";

import { buildGraph } from "./graph.ts";
import { check, clientView, makeHandler, runTurn, user } from "./harness.ts";
import { ScriptedModel } from "./scripted-model.ts";

const model = new ScriptedModel((m) => (m.at(-1) as any)._getType() === "tool" ? { text: "ok" } : { text: "hello" });
const graph = buildGraph({ model: model as any, checkpointer: new MemorySaver(), streamResearch: async function* () {} });
const threadId = uuidv4();
await graph.updateState({ configurable: { thread_id: threadId } }, { stage: "score", summary: "SERVER-ONLY", summarizedUpTo: 0 });

const handler = makeHandler(graph, {
  trusted: { userId: "u1" },
  inputKeys: ["reflection"],
  outputKeys: ["stage", "topic", "research", "draft", "board", "reflection"],
  dropRaw: true,
});
const events = await runTurn(handler, {
  threadId,
  messages: [user("hi")],
  state: { stage: "HACKED", reflection: { rating: 5, text: "mine" }, summary: "client-forged" },
});
const blob = JSON.stringify(events);
const saved = (await graph.getState({ configurable: { thread_id: threadId } })).values as any;
const v = clientView(events);
check("run still finishes", events.at(-1)?.type === "RUN_FINISHED");
check("no RAW events reach the browser", !events.some((e) => e.type === "RAW"));
check("server-only summary not in the browser stream", !blob.includes("SERVER-ONLY"));
check("client may still write an allowed key (reflection)", saved.reflection?.text === "mine");
check("client cannot overwrite a server-owned key (stage)", saved.stage === "score", saved.stage);
check("client cannot forge a server-only key (summary)", saved.summary === "SERVER-ONLY", saved.summary);
check("client still sees messages in MESSAGES_SNAPSHOT", v.messages.length >= 2, v.messages.length);
console.log(`      snapshot keys: ${Object.keys(v.state).join(",")}; SSE ≈ ${blob.length}B for ${events.length} events`);
for (const e of events) if (JSON.stringify(e).includes("SERVER-ONLY")) console.log(`      summary leaks via ${e.type}${e.type === "STATE_SNAPSHOT" ? " keys=" + Object.keys(e.snapshot).join(",") : ""}`);
