/** A3/A7/A9 edge cases: parallel same-key writes, a throwing tool, Stop mid-run. */
import "./env.ts";

import { MemorySaver } from "@langchain/langgraph";
import { Command } from "@langchain/langgraph";
import { tool, toolErrorMiddleware, ToolMessage } from "langchain";
import { v4 as uuidv4 } from "uuid";
import { z } from "zod";

import { buildGraph } from "./graph.ts";
import { AGENT_ID, check, clientView, makeHandler, runTurn, summarize, user } from "./harness.ts";
import { ScriptedModel } from "./scripted-model.ts";

const setStage = tool(
  async ({ to }, rt: any) => new Command({ update: { stage: to, messages: [new ToolMessage({ content: `stage=${to}`, tool_call_id: rt.toolCallId, name: "setStage" })] } }),
  { name: "setStage", description: "x", schema: z.object({ to: z.string() }) },
);
const boom = tool(async () => { throw new Error("provider exploded"); }, { name: "boom", description: "x", schema: z.object({}) });
const slow = tool(async (_a, rt: any) => {
  for (let i = 0; i < 50; i++) {
    if (rt.config?.signal?.aborted) throw new Error("aborted in tool");
    await new Promise((r) => setTimeout(r, 100));
  }
  return "slow done";
}, { name: "slow", description: "x", schema: z.object({}) });

const model = new ScriptedModel((m) => {
  const last = m.at(-1) as any;
  if (last._getType() === "tool") return { text: `after tool: ${String(last.content).slice(0, 60)}` };
  const t = String(last.content);
  if (t === "parallel") return { toolCalls: [{ name: "setStage", args: { to: "a" } }, { name: "setStage", args: { to: "b" } }] };
  if (t === "boom") return { toolCalls: [{ name: "boom", args: {} }] };
  if (t === "slow") return { toolCalls: [{ name: "slow", args: {} }] };
  return { text: "hi" };
});

const graph = buildGraph({ model: model as any, checkpointer: new MemorySaver(), streamResearch: async function* () {}, extraTools: [setStage, boom, slow],
  extraMiddleware: process.env.TOOL_ERRORS ? [toolErrorMiddleware({ onError: (e: any) => `Tool failed: ${e?.name ?? "Error"}` })] : [] });
const handler = makeHandler(graph, { trusted: { userId: "u1" }, dropRaw: true });

// parallel writes to one LastValue key
{
  const ev = await runTurn(handler, { threadId: uuidv4(), messages: [user("parallel")] });
  const err = ev.find((e) => e.type === "RUN_ERROR");
  console.log("      parallel:", JSON.stringify(summarize(ev)));
  check("two tool calls writing `stage` in one step fail the run (LastValue)", !!err, String(err?.message ?? "no error").slice(0, 140));
}

// a throwing tool
{
  const ev = await runTurn(handler, { threadId: uuidv4(), messages: [user("boom")] });
  const err = ev.find((e) => e.type === "RUN_ERROR");
  const result = ev.find((e) => e.type === "TOOL_CALL_RESULT");
  console.log("      boom:", JSON.stringify(summarize(ev)));
  check("a throwing tool: model gets an error ToolMessage (run continues)", !err && !!result, err ? `RUN_ERROR: ${String(err.message).slice(0, 120)}` : String(result?.content).slice(0, 120));
}

// Stop mid-run through the runtime's stop route
{
  const threadId = uuidv4();
  const t0 = Date.now();
  const running = runTurn(handler, { threadId, messages: [user("slow")] });
  await new Promise((r) => setTimeout(r, 1500));
  const stopRes = await handler(new Request(`http://localhost/api/copilotkit/agent/${AGENT_ID}/stop/${threadId}`, { method: "POST" }));
  console.log(`      stop route: HTTP ${stopRes.status} ${await stopRes.text()}`);
  const ev = await running;
  const took = Date.now() - t0;
  console.log("      slow:", JSON.stringify(summarize(ev)), `${took}ms`);
  check("Stop ends the run well before the tool's 5s", took < 4000, `${took}ms`);
  const saved = (await graph.getState({ configurable: { thread_id: threadId } })).values as any;
  const types = (saved.messages ?? []).map((m: any) => m._getType()).join(",");
  check("after Stop the checkpoint has no dangling tool call (ai without tool result)", !/ai$/.test(types) || !(saved.messages.at(-1)?.tool_calls?.length), types);
  const next = await runTurn(handler, { threadId, messages: [...clientView(ev).messages, user("hello")] });
  check("the thread still accepts the next turn after Stop", next.at(-1)?.type === "RUN_FINISHED", next.find((e) => e.type === "RUN_ERROR")?.message?.slice(0, 160));
}
