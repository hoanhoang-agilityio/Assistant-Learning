/**
 * S1 (H1 in-process), S2 (copilotkitMiddleware + createAgent), S3 (drafts
 * mid-tool), S4 (client setState vs checkpoint), S5 (forwardedProps),
 * S6 (a2ui_operations from a LangChain tool), S7 (context hook), S8 (secret
 * leakage) — with a scripted model, so every run is deterministic.
 *
 *   tsx src/spike-core.ts [ag-ui|copilotkit|none]
 */
import "./env.ts";

import { v4 as uuidv4 } from "uuid";

import { BaseTracer, type Run } from "@langchain/core/tracers/base";
import { parsePartialJson } from "@langchain/core/output_parsers";
import { MemorySaver } from "@langchain/langgraph";

import { buildGraph, type EmitMode } from "./graph.ts";
import { check, clientView, makeHandler, runTurn, summarize, user } from "./harness.ts";
import { ScriptedModel } from "./scripted-model.ts";

class Collector extends BaseTracer {
  name = "collector";
  runs: Run[] = [];
  protected async persistRun(run: Run) {
    this.runs.push(run);
  }
  onRunCreate(run: Run) {
    this.runs.push(run);
  }
}

const emitMode = (process.argv[2] ?? "ag-ui") as EmitMode;
console.log(`\n=== spike-core, emitMode=${emitMode} ===`);

const SEALED = "SEALED-KEY-abc123";
const CLERK_JWT = "Bearer clerk-jwt-xyz";
const TRUSTED_KEY = "sk-TRUSTED-999";

const supervisor = new ScriptedModel((messages) => {
  const last = messages.at(-1) as any;
  const lastUser = [...messages].reverse().find((m: any) => m._getType() === "human") as any;
  const text = String(lastUser?.content ?? "");
  if (last._getType() === "tool") return { text: `Done: ${String(last.content).slice(0, 40)}` };
  if (text.startsWith("research")) return { toolCalls: [{ name: "research", args: { topic: "photosynthesis" } }] };
  if (text.startsWith("whoami")) return { toolCalls: [{ name: "whoami", args: {} }] };
  if (text.startsWith("card")) {
    return {
      toolCalls: [{
        name: "renderSurface",
        args: {
          target: "chat",
          title: "Card",
          components: [
            { id: "root", component: "Panel", title: "Hello", children: ["p1"] },
            { id: "p1", component: "Paragraph", text: "A paragraph" },
          ],
        },
      }],
    };
  }
  if (text.startsWith("badcard")) {
    return {
      toolCalls: [{
        name: "renderSurface",
        args: { target: "chat", title: "Bad", components: [{ id: "root", component: "Panel", title: "x", children: ["missing"] }] },
      }],
    };
  }
  return { text: "Hi there" };
});

const researchJson = JSON.stringify({ title: "Photosynthesis", summary: "Plants turn light into sugar.", keyInsight: "Chlorophyll absorbs light." });
const inner = new ScriptedModel(() => ({ text: researchJson }));

const seen1: any[] = [];
const graph = buildGraph({
  model: supervisor as any,
  checkpointer: new MemorySaver(),
  emitMode,
  seen: seen1,
  streamResearch: async function* (_topic, config) {
    let acc = "";
    for await (const chunk of await inner.stream("go", config)) {
      acc += chunk.content;
      const partial = parsePartialJson(acc);
      if (partial) yield partial;
    }
  },
});

const collector = new Collector();
let lastRunConfig: any;
const handler = makeHandler(graph, {
  trusted: { userId: "user_clerk_1", apiKey: TRUSTED_KEY },
  pickForwarded: (p) => ({ settings: p.settings, a2uiAction: p.a2uiAction }),
  onRunConfig: (c) => {
    lastRunConfig = c;
    (c as any).callbacks = [collector];
  },
});

const threadId = uuidv4();
let results: boolean[] = [];

// ---------- Turn 1: research (S1, S2, S3) ----------
const m1 = [user("research photosynthesis")];
const e1 = await runTurn(handler, { threadId, messages: m1, state: {} });
console.log("turn1 events:", summarize(e1));
const v1 = clientView(e1);
results.push(check("S1 run completes through CopilotRuntime → LangGraphAgent → in-process graph", e1.at(-1)?.type === "RUN_FINISHED", e1.at(-1)?.type));
results.push(check("S2 supervisor tool call streamed as TOOL_CALL_START/ARGS", e1.some((e) => e.type === "TOOL_CALL_START" && e.toolCallName === "research") && e1.some((e) => e.type === "TOOL_CALL_ARGS")));
results.push(check("S2 tool result streamed", e1.some((e) => e.type === "TOOL_CALL_RESULT")));
results.push(check("S2 final text streamed", e1.some((e) => e.type === "TEXT_MESSAGE_CONTENT" && e.delta.includes("Done") || e.type === "TEXT_MESSAGE_CONTENT")));
const draftSnaps = v1.snapshots.filter((s: any) => s.draft?.task === "research");
results.push(check(`S3 draft STATE_SNAPSHOTs mid-tool (${emitMode})`, draftSnaps.length > 0, `${draftSnaps.length} snapshots with draft`));
const customDrafts = e1.filter((e) => e.type === "CUSTOM" && /emit/.test(e.name));
console.log("      CUSTOM emit events:", customDrafts.length, [...new Set(customDrafts.map((e) => e.name))]);
results.push(check("S3 final state: research set, draft cleared", v1.state.research?.title === "Photosynthesis" && v1.state.draft === null, { research: v1.state.research?.title, draft: v1.state.draft }));
const innerLeak = e1.filter((e) => (e.type === "TEXT_MESSAGE_CONTENT" || e.type === "TOOL_CALL_ARGS") && /keyInsight|Chlorophyll/.test(String(e.delta)));
results.push(check("S3 inner model tokens do NOT leak into chat (emit-messages:false)", innerLeak.length === 0, `${innerLeak.length} leaked deltas`));
const snapOrder = v1.snapshots.map((s: any) => (s.draft ? "D" : s.research ? "R" : "-")).join("");
console.log("      snapshot sequence (D=draft, R=research, -=neither):", snapOrder);
results.push(check("S3 no stale draft snapshot after the final research snapshot", !/R.*D/.test(snapOrder.replace(/^-+/, "")) || !snapOrder.endsWith("D")));

// ---------- Turn 2: client setState + forwardedProps + headers (S4, S5, S8) ----------
const clientState = { ...v1.state, reflection: { rating: 4, text: "client edit" }, stage: "idle-stale-from-client" };
const m2 = [...v1.messages, user("whoami")];
const e2 = await runTurn(handler, {
  threadId,
  messages: m2,
  state: clientState,
  forwardedProps: { settings: { level: "beginner" }, config: { configurable: { userId: "FORGED" } }, context: { userId: "FORGED2" } },
  headers: { "x-openai-key-sealed": SEALED, authorization: CLERK_JWT },
});
const v2 = clientView(e2);
const who = JSON.parse(e2.find((e) => e.type === "TOOL_CALL_RESULT" && String(e.content).includes("context"))?.content ?? "{}");
console.log("      whoami:", JSON.stringify(who));
const saved = (await graph.getState({ configurable: { thread_id: threadId } })).values as any;
results.push(check("S4 client setState edit (reflection) persisted to checkpoint", saved.reflection?.text === "client edit"));
results.push(check("S4 client's stale key OVERWRITES checkpoint (stage)", saved.stage === "idle-stale-from-client", saved.stage));
results.push(check("S5 forwardedProps.settings reaches graph only via our client adapter (context)", who.context?.settings?.level === "beginner", who.context?.settings));
results.push(check("S5 trusted userId in context, from server not request", who.context?.userId === "user_clerk_1"));
results.push(check("H1 forged forwardedProps.config/context do not reach the graph", !JSON.stringify(who).includes("FORGED"), who.configurableKeys?.filter((k: string) => !k.startsWith("__"))));
{
  const eS = await runTurn(handler, {
    threadId, messages: v2.messages, state: v2.state,
    forwardedProps: { a2uiAction: { userAction: { name: "submit_quiz", surfaceId: "quiz-1", context: { answers: { q1: 2 } } } } },
  });
  const afterS = (await graph.getState({ configurable: { thread_id: threadId } })).values as any;
  const synth = afterS.messages.filter((m: any) => m._getType() === "tool" && String(m.content).includes("User performed action"));
  results.push(check("S5 Submit (no user message) → A2UIMiddleware appends a synthetic ai+tool pair, persisted in the checkpoint", synth.length === 1, `${synth.length} synthetic; ` + String(synth[0]?.content ?? "").slice(0, 110)));
  results.push(check("S5 a2uiAction reachable in the graph via our client adapter (context)", !!lastRunConfig?.context?.a2uiAction, lastRunConfig?.context?.a2uiAction?.userAction?.name));
  console.log("      submit turn events:", JSON.stringify(summarize(eS)));
  v2.messages = clientView(eS).messages; v2.state = clientView(eS).state;
}
results.push(check("S8 forwarded headers reach configurable (copilotkit_forwarded_headers)", who.forwardedHeaders?.length > 0, who.forwardedHeaders));
const t2Settings = seen1.at(-1)?.modelSettings;
results.push(check("S8 forwarded x-* headers are NOT added to the OpenAI request (no withForwardedHeaders scope in H1)", !t2Settings?.headers, t2Settings?.headers ?? "none"));

// search checkpoints + traces for secrets
const tuples: any[] = [];
for await (const t of (graph as any).checkpointer.list({ configurable: { thread_id: threadId } })) tuples.push(t);
for (const t of tuples) {
  const b = JSON.stringify({ metadata: t.metadata, config: t.config });
  for (const sec of [SEALED, TRUSTED_KEY]) if (b.includes(sec)) { const i = b.indexOf(sec); console.log(`      ${sec} in checkpoint metadata/config: …${b.slice(Math.max(0, i - 120), i + 20)}…`); break; }
}
const cpBlob = JSON.stringify(tuples.map((t) => ({ metadata: t.metadata, config: t.config, checkpoint: t.checkpoint })));
const traceBlob = JSON.stringify(collector.runs.map((r) => ({ inputs: r.inputs, outputs: r.outputs, extra: r.extra, tags: r.tags })));
for (const [name, secret] of [["sealed header", SEALED], ["clerk jwt", CLERK_JWT], ["trusted key (context)", TRUSTED_KEY]] as const) {
  console.log(`      ${name}: checkpoint=${cpBlob.includes(secret)} trace=${traceBlob.includes(secret)}`);
}
for (const r of collector.runs) {
  for (const f of ["inputs", "outputs", "extra", "tags"] as const) {
    if (JSON.stringify((r as any)[f] ?? null).includes(TRUSTED_KEY)) {
      const blob = JSON.stringify((r as any)[f]); const i = blob.indexOf(TRUSTED_KEY);
      console.log(`      trusted key in trace run "${r.name}" (${r.run_type}).${f}: …${blob.slice(Math.max(0, i - 90), i + 20)}…`);
    }
  }
}
results.push(check("S8 trusted key in context is NOT in checkpoints", !cpBlob.includes(TRUSTED_KEY)));
results.push(check("S8 trusted key in context is NOT in traces", !traceBlob.includes(TRUSTED_KEY)));

// ---------- Turn 3: A2UI chat card (S6) ----------
const e3 = await runTurn(handler, { threadId, messages: [...v2.messages, user("card please")], state: v2.state });
const act = e3.filter((e) => e.type === "ACTIVITY_SNAPSHOT");
results.push(check("S6 a2ui_operations in a LangChain tool result → ACTIVITY_SNAPSHOT (a2ui-surface)", act.some((a) => a.activityType === "a2ui-surface" && a.content?.a2ui_operations?.length), act.map((a) => a.activityType)));
const e4 = await runTurn(handler, { threadId, messages: [...clientView(e3).messages, user("badcard")], state: clientView(e3).state });
const bad = e4.find((e) => e.type === "TOOL_CALL_RESULT")?.content ?? "";
results.push(check("S6 validateA2UIComponents reused as-is: invalid tree → error for the model", String(bad).includes("error"), String(bad).slice(0, 120)));

// ---------- S7: context builder ----------
await graph.updateState({ configurable: { thread_id: threadId } }, { summary: "Earlier we researched photosynthesis.", summarizedUpTo: 4 });
const before = (await graph.getState({ configurable: { thread_id: threadId } })).values as any;
const seenArr: any[] = [];
const g7 = buildGraph({ model: supervisor as any, checkpointer: (graph as any).checkpointer, emitMode, seen: seenArr, streamResearch: async function* () {} });
const h7 = makeHandler(g7, { trusted: { userId: "user_clerk_1" } });
const s7state = clientView(e4).state;
delete s7state.summary; // client doesn't know about summary fields
delete s7state.summarizedUpTo;
const e7 = await runTurn(h7, { threadId, messages: [...clientView(e4).messages, user("hello")], state: s7state });
const after = (await g7.getState({ configurable: { thread_id: threadId } })).values as any;
const got = seenArr[0] ?? [];
results.push(check("S7 model saw summary system message", got.some((m: any) => String(m.content).startsWith("Summary of earlier")), got.map((m: any) => m._getType()).join(",")));
results.push(check("S7 model saw only messages after summarizedUpTo", got.length < after.messages.length, `${got.length} seen vs ${after.messages.length} stored`));
results.push(check("S7 checkpoint messages not trimmed (append only)", after.messages.length === before.messages.length + 2, `${before.messages.length} → ${after.messages.length}`));
results.push(check("S7 summary fields survive a run where the client omits them", after.summary === "Earlier we researched photosynthesis.", after.summary));
console.log("turn7 events:", summarize(e7));

console.log(`\n${results.filter(Boolean).length}/${results.length} checks passed`);

// snapshot payloads: full state every time? includes messages?
{
  const snaps = e1.filter((e) => e.type === "STATE_SNAPSHOT");
  const sizes = snaps.map((s) => JSON.stringify(s.snapshot).length);
  console.log(`      turn1 STATE_SNAPSHOT: n=${snaps.length}, max=${Math.max(...sizes)}B, total=${sizes.reduce((a, b) => a + b, 0)}B, keys=${Object.keys(snaps.at(-1)?.snapshot ?? {}).join(",")}`);
  const raw = e1.filter((e) => e.type === "RAW");
  console.log(`      turn1 RAW events: n=${raw.length}, total=${raw.reduce((a, r) => a + JSON.stringify(r).length, 0)}B`);
  const all = e1.reduce((a, r) => a + JSON.stringify(r).length, 0);
  console.log(`      turn1 whole SSE payload ≈ ${all}B for ${e1.length} events`);
}

// Does anything server-only reach the BROWSER stream?
{
  const turns = { e1, e2, e3, e4, e7 };
  for (const [name, evs] of Object.entries(turns)) {
    const blob = JSON.stringify(evs);
    const hits = [["trusted key", TRUSTED_KEY], ["sealed header", SEALED], ["userId", "user_clerk_1"]]
      .filter(([, s]) => blob.includes(s)).map(([n]) => n);
    const byType = [...new Set(evs.filter((e) => hits.length && JSON.stringify(e).includes(TRUSTED_KEY)).map((e) => e.type))];
    console.log(`      browser stream ${name}: ${hits.length ? "LEAKS " + hits.join(", ") + " via " + byType.join(",") : "clean"}`);
  }
}
{
  const raw = e7.filter((e) => e.type === "RAW" && JSON.stringify(e).includes("Earlier we researched"));
  const snap = e7.filter((e) => e.type === "STATE_SNAPSHOT" && JSON.stringify(e).includes("Earlier we researched"));
  console.log(`      server-only 'summary' reaches browser: RAW=${raw.length} events, STATE_SNAPSHOT=${snap.length} events`);
}
