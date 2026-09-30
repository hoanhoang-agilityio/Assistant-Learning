/**
 * S2/S3 against the real model, A1 (structured output streams partials?),
 * S8 (does a ChatOpenAI built with the key per request leak it into traces?).
 */
import "./env.ts";

import { BaseTracer, type Run } from "@langchain/core/tracers/base";
import { MemorySaver } from "@langchain/langgraph";
import { ChatOpenAI } from "@langchain/openai";
import { v4 as uuidv4 } from "uuid";

import { buildGraph, ResearchSchema } from "./graph.ts";
import { check, clientView, makeHandler, runTurn, summarize, user } from "./harness.ts";

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

const apiKey = process.env.OPENAI_API_KEY!;
const makeModel = () => new ChatOpenAI({ model: "gpt-5.4-mini", apiKey, reasoning: { effort: "low" }, useResponsesApi: true });

let partials = 0;
const graph = buildGraph({
  model: makeModel(),
  checkpointer: new MemorySaver(),
  emitMode: "ag-ui",
  streamResearch: async function* (topic, config) {
    const structured = makeModel().withStructuredOutput(ResearchSchema, { name: "research" });
    for await (const partial of await structured.stream(
      `Research "${topic}" for a beginner. Keep each field to one sentence.`,
      config,
    )) {
      partials++;
      yield partial;
    }
  },
});

const collector = new Collector();
const handler = makeHandler(graph, {
  trusted: { userId: "u1" },
  dropRaw: true,
  outputKeys: ["stage", "topic", "research", "draft", "board", "reflection"],
  onRunConfig: (c: any) => {
    c.callbacks = [collector];
  },
});

const t0 = Date.now();
const events = await runTurn(handler, {
  threadId: uuidv4(),
  messages: [user("Use the research tool on the topic 'ocean tides', then reply with one short sentence.")],
});
const ms = Date.now() - t0;
console.log("events:", JSON.stringify(summarize(events)));
const v = clientView(events);
const texts = events.filter((e) => e.type === "TEXT_MESSAGE_CONTENT").map((e) => e.delta).join("");
check("real model: run finishes", events.at(-1)?.type === "RUN_FINISHED", `${ms}ms`);
check("real model: research tool called and streamed", events.some((e) => e.type === "TOOL_CALL_START" && e.toolCallName === "research"));
check("A1 withStructuredOutput streams partial objects", partials > 2, `${partials} partials`);
const drafts = v.snapshots.filter((s: any) => s.draft?.task === "research").length;
check("S3 drafts reached the client", drafts > 2, `${drafts} draft snapshots`);
check("final research in state", !!v.state.research?.title, v.state.research?.title);
check("inner structured call did not leak into chat text", !/keyInsight|"summary"/.test(texts), texts.slice(0, 120));
const leakedToolCalls = events.filter((e) => e.type === "TOOL_CALL_START" && e.toolCallName !== "research");
check("inner structured call did not surface as a tool call", leakedToolCalls.length === 0, leakedToolCalls.map((e) => e.toolCallName));
const reasoning = events.filter((e) => String(e.type).startsWith("REASONING"));
console.log(`      reasoning events streamed to client: ${reasoning.length}`);
const trace = JSON.stringify(collector.runs.map((r) => ({ inputs: r.inputs, outputs: r.outputs, extra: r.extra, serialized: r.serialized })));
check("S8 API key built into ChatOpenAI is NOT in traces", !trace.includes(apiKey));
check("S8 API key NOT in the browser stream", !JSON.stringify(events).includes(apiKey));
console.log(`      final text: ${texts.slice(0, 160)}`);
const err = events.find((e) => e.type === "RUN_ERROR");
if (err) console.log("      RUN_ERROR:", String(err.message).replace(apiKey, "<key>").slice(0, 500));
