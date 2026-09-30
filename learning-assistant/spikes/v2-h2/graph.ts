import { copilotkitMiddleware } from "@copilotkit/sdk-js/langgraph";
import { dispatchCustomEvent } from "@langchain/core/callbacks/dispatch";
import { Command } from "@langchain/langgraph";
import { createAgent, tool, ToolMessage } from "langchain";
import { z } from "zod";

import { ScriptedModel } from "./scripted-model.ts";

const model = new ScriptedModel((messages) => {
  const last = messages.at(-1) as any;
  if (last._getType() === "tool") return { text: "done" };
  const text = String(last.content);
  if (text.startsWith("research")) return { toolCalls: [{ name: "research", args: { topic: "tides" } }] };
  if (text.startsWith("whoami")) return { toolCalls: [{ name: "whoami", args: {} }] };
  return { text: "hello from H2" };
});

const research = tool(
  async ({ topic }, runtime: any) => {
    for (const partial of [{ title: "T" }, { title: "Tides", summary: "Moon" }]) {
      await dispatchCustomEvent("manually_emit_state", { ...runtime.state, draft: { task: "research", research: partial } }, runtime.config);
    }
    return new Command({
      update: {
        research: { title: "Tides", summary: "Moon", keyInsight: "Gravity" }, topic, draft: null,
        messages: [new ToolMessage({ content: "ok", tool_call_id: runtime.toolCallId, name: "research" })],
      },
    });
  },
  { name: "research", description: "research", schema: z.object({ topic: z.string() }) },
);

const whoami = tool(
  async (_a, runtime: any) => JSON.stringify({
    contextKeys: Object.keys(runtime.context ?? {}),
    context: runtime.context,
    configurable: Object.fromEntries(Object.entries(runtime.config?.configurable ?? {}).filter(([k]) => !k.startsWith("__") && !k.startsWith("checkpoint"))),
  }),
  { name: "whoami", description: "debug", schema: z.object({}) },
);

export const agent = createAgent({
  model: model as any,
  tools: [research, whoami],
  systemPrompt: "supervisor",
  stateSchema: z.object({
    stage: z.string().default("idle"),
    topic: z.string().nullable().default(null),
    research: z.any().nullable().default(null),
    draft: z.any().nullable().default(null),
    reflection: z.any().nullable().default(null),
  }) as any,
  contextSchema: z.object({ userId: z.string().optional(), settings: z.any().optional() }) as any,
  middleware: [copilotkitMiddleware] as any,
});
