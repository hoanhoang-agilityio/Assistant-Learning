/** S9b: a real new process — what does /connect return for a thread that only exists in Postgres? */
import "./env.ts";

import { readFileSync } from "node:fs";

import { PostgresSaver } from "@langchain/langgraph-checkpoint-postgres";
import { v4 as uuidv4 } from "uuid";

import { DB_URL } from "./env.ts";
import { CheckpointRunner } from "./checkpoint-runner.ts";
import { buildGraph } from "./graph.ts";
import { AGENT_ID, check, makeHandler } from "./harness.ts";
import { ScriptedModel } from "./scripted-model.ts";

const threadId = readFileSync(new URL("../.last-thread", import.meta.url), "utf8").trim();
const saver = PostgresSaver.fromConnString(DB_URL);
const graph = buildGraph({ model: new ScriptedModel(() => ({ text: "x" })) as any, checkpointer: saver, streamResearch: async function* () {} });
const outputKeys = ["stage", "topic", "research", "draft", "board", "reflection"];
const handler = makeHandler(graph, {
  trusted: { userId: "u1" },
  ...(process.env.RUNNER === "checkpoint" ? { runner: new CheckpointRunner(graph, outputKeys) } : {}),
});
const res = await handler(
  new Request(`http://localhost/api/copilotkit/agent/${AGENT_ID}/connect`, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify({ threadId, runId: uuidv4(), state: {}, messages: [], tools: [], context: [], forwardedProps: {} }),
  }),
);
const events = (await res.text()).split("\n").filter((l) => l.startsWith("data: ")).map((l) => JSON.parse(l.slice(6)));
console.log(`      /connect in a fresh process: HTTP ${res.status}, events=${events.map((e) => e.type).join(",") || "none"}`);
check("fresh-process /connect restores messages from Postgres", events.some((e) => e.type === "MESSAGES_SNAPSHOT" && e.messages.length > 0));
const s = await graph.getState({ configurable: { thread_id: threadId } });
console.log(`      but the checkpoint has ${(s.values as any).messages?.length} messages`);
const snap = events.find((e) => e.type === "STATE_SNAPSHOT")?.snapshot;
if (snap) check("state snapshot restored and filtered to output keys", snap.research?.title === "Tides" && !("summary" in snap), Object.keys(snap));
await saver.end();
