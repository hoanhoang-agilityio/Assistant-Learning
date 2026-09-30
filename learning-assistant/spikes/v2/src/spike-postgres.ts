/**
 * S9: PostgresSaver (setup once), survives a "restart", what the runtime's
 * /connect (page reload) returns afterwards, deleteThread, and PostgresStore.
 */
import "./env.ts";

import { PostgresSaver } from "@langchain/langgraph-checkpoint-postgres";
import { PostgresStore } from "@langchain/langgraph-checkpoint-postgres/store";
import pg from "pg";
import { v4 as uuidv4 } from "uuid";

import { DB_URL } from "./env.ts";
import { buildGraph } from "./graph.ts";
import { AGENT_ID, check, clientView, makeHandler, runTurn, user } from "./harness.ts";
import { ScriptedModel } from "./scripted-model.ts";

const model = () =>
  new ScriptedModel((m) => {
    const last = m.at(-1) as any;
    if (last._getType() === "tool") return { text: "researched" };
    return String(last.content).startsWith("research")
      ? { toolCalls: [{ name: "research", args: { topic: "tides" } }] }
      : { text: "hello again" };
  });
const streamResearch = async function* () {
  yield { title: "Tides" };
  yield { title: "Tides", summary: "Moon pulls water.", keyInsight: "Gravity." };
};

// --- process 1 ---
const t0 = Date.now();
const saver1 = PostgresSaver.fromConnString(DB_URL);
await saver1.setup();
await saver1.setup(); // idempotent?
check("setup() is idempotent (ran twice)", true, `${Date.now() - t0}ms`);

const threadId = uuidv4();
const g1 = buildGraph({ model: model() as any, checkpointer: saver1, streamResearch, emitMode: "ag-ui" });
const h1 = makeHandler(g1, { trusted: { userId: "u1" } });
const e1 = await runTurn(h1, { threadId, messages: [user("research tides")] });
const v1 = clientView(e1);
check("turn 1 on Postgres finishes", e1.at(-1)?.type === "RUN_FINISHED");
await saver1.end();

// --- process 2 ("restart": new saver, new graph, new runtime) ---
const saver2 = PostgresSaver.fromConnString(DB_URL);
const g2 = buildGraph({ model: model() as any, checkpointer: saver2, streamResearch, emitMode: "ag-ui" });
const s2 = (await g2.getState({ configurable: { thread_id: threadId } })).values as any;
check("state survives restart", s2.research?.title === "Tides" && s2.messages.length === v1.messages.length, `${s2.messages.length} messages`);

const h2 = makeHandler(g2, { trusted: { userId: "u1" } });
const res = await h2(
  new Request(`http://localhost/api/copilotkit/agent/${AGENT_ID}/connect`, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify({ threadId, runId: uuidv4(), state: {}, messages: [], tools: [], context: [], forwardedProps: {} }),
  }),
);
const connectText = await res.text();
const connectEvents = connectText.split("\n").filter((l) => l.startsWith("data: ")).map((l) => JSON.parse(l.slice(6)));
console.log(`      /connect after restart: HTTP ${res.status}, events=${connectEvents.map((e) => e.type).join(",") || "none"}`);
check(
  "/connect after restart restores messages from the checkpoint",
  connectEvents.some((e) => e.type === "MESSAGES_SNAPSHOT" && e.messages.length > 0),
);

// A reloaded client that only sends the new message (no history, no state):
const e2 = await runTurn(h2, { threadId, messages: [user("hi")], state: {} });
const v2 = clientView(e2);
check("new turn with no client history still continues the thread", v2.messages.length === v1.messages.length + 2, `${v1.messages.length} → ${v2.messages.length}`);
check("…and keeps server state (research)", v2.state.research?.title === "Tides");

if (process.env.KEEP) {
  const { writeFileSync } = await import("node:fs");
  writeFileSync(new URL("../.last-thread", import.meta.url), threadId);
  console.log(`      kept thread ${threadId} for spike-connect`);
  await saver2.end();
  process.exit(0);
}

// --- deleteThread ---
const pool = new pg.Pool({ connectionString: DB_URL });
const count = async () =>
  Number((await pool.query("select count(*) from checkpoints where thread_id = $1", [threadId])).rows[0].count);
const before = await count();
await saver2.deleteThread(threadId);
const after = await count();
const blobs = Number((await pool.query("select count(*) from checkpoint_blobs where thread_id = $1", [threadId])).rows[0].count);
const writes = Number((await pool.query("select count(*) from checkpoint_writes where thread_id = $1", [threadId])).rows[0].count);
check("deleteThread removes checkpoints, blobs, writes", after === 0 && blobs === 0 && writes === 0, { before, after, blobs, writes });
const tables = (await pool.query("select table_name from information_schema.tables where table_schema='public' order by 1")).rows.map((r) => r.table_name);
console.log(`      tables after saver.setup(): ${tables.join(", ")}`);

// --- PostgresStore (long-term memory, per user namespace) ---
const store = PostgresStore.fromConnString(DB_URL);
await store.setup();
await store.put(["users", "u1", "profile"], "main", { level: "beginner", language: "vi" });
await store.put(["users", "u2", "profile"], "main", { level: "expert" });
const got = await store.get(["users", "u1", "profile"], "main");
const listed = await store.search(["users", "u1"]);
check("PostgresStore put/get works", (got?.value as any)?.level === "beginner");
check("PostgresStore search is namespace-scoped (no u2 rows under u1)", listed.every((i) => i.namespace[1] === "u1"), listed.length);
await store.delete(["users", "u1", "profile"], "main");
check("PostgresStore delete works", (await store.get(["users", "u1", "profile"], "main")) === null);
const tables2 = (await pool.query("select table_name from information_schema.tables where table_schema='public' order by 1")).rows.map((r) => r.table_name);
console.log(`      tables after store.setup(): ${tables2.filter((t) => !tables.includes(t)).join(", ")}`);
await store.stop?.();
await saver2.end();
await pool.end();
