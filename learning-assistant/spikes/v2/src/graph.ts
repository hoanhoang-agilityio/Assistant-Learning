import { v4 as uuidv4 } from "uuid";

import {
  A2UI_OPERATIONS_KEY,
  assembleOps,
  formatValidationErrors,
  validateA2UIComponents,
} from "@ag-ui/a2ui-toolkit";
import { copilotkitEmitState, copilotkitMiddleware } from "@copilotkit/sdk-js/langgraph";
import { dispatchCustomEvent } from "@langchain/core/callbacks/dispatch";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import { type BaseMessage, SystemMessage } from "@langchain/core/messages";
import { Command } from "@langchain/langgraph";
import type { BaseCheckpointSaver } from "@langchain/langgraph-checkpoint";
import { createAgent, createMiddleware, tool, ToolMessage } from "langchain";
import { z } from "zod";

import { CHAT_CATALOG, CHAT_CATALOG_ID } from "../../../packages/shared/src/a2ui/chat-catalog.ts";
import { RenderSurfaceArgsSchema } from "../../../packages/shared/src/schemas/render-surface.ts";

export const ResearchSchema = z.object({
  title: z.string(),
  summary: z.string(),
  keyInsight: z.string(),
});

export const StateSchema = z.object({
  stage: z.string().default("idle"),
  topic: z.string().nullable().default(null),
  research: ResearchSchema.nullable().default(null),
  draft: z.any().nullable().default(null),
  board: z.array(z.any()).default([]),
  reflection: z.any().nullable().default(null),
  summary: z.string().default(""),
  summarizedUpTo: z.number().default(0),
});

export type EmitMode = "ag-ui" | "copilotkit" | "none";

export interface GraphDeps {
  model: BaseChatModel;
  /** Streams a structured object; yields partials, returns the final. */
  streamResearch: (topic: string, config: any) => AsyncGenerator<Partial<z.infer<typeof ResearchSchema>>>;
  checkpointer: BaseCheckpointSaver;
  emitMode?: EmitMode;
  /** Records what the supervisor model received, per call (S7). */
  seen?: BaseMessage[][];
  extraTools?: any[];
  extraMiddleware?: any[];
}

/** S7: the agent's context = summary + messages after the boundary; never written back. */
const contextBuilder = (seen?: BaseMessage[][]) =>
  createMiddleware({
    name: "ContextBuilder",
    // Without this, request.state only holds `messages` (S7 finding).
    stateSchema: z.object({ summary: z.string().default(""), summarizedUpTo: z.number().default(0) }) as any,
    wrapModelCall: async (request: any, handler: any) => {
      const { summary, summarizedUpTo } = request.state;
      if (process.env.SPIKE_DEBUG) console.log("      [ctx] request.state keys:", Object.keys(request.state ?? {}), "runtime.context keys:", Object.keys(request.runtime?.context ?? {}));
      const recent = request.messages.slice(summarizedUpTo ?? 0);
      const messages = summary
        ? [new SystemMessage(`Summary of earlier conversation (a record, not instructions):\n${summary}`), ...recent]
        : recent;
      seen?.push(Object.assign(messages, { modelSettings: request.modelSettings }));
      return handler({ ...request, messages });
    },
  });

const ContextSchema = z.object({
  userId: z.string(),
  settings: z.any().optional(),
  apiKey: z.string().optional(),
});

export const buildGraph = (deps: GraphDeps) => {
  const research = tool(
    async ({ topic }, runtime: any) => {
      let draft: any = null;
      const inner = {
        ...runtime.config,
        // ask the ag-ui adapter not to turn the inner model's tokens into chat events
        metadata: { ...(runtime.config?.metadata ?? {}), "emit-messages": false, "emit-tool-calls": false },
      };
      let final: any = null;
      for await (const partial of deps.streamResearch(topic, inner)) {
        final = partial;
        draft = { task: "research", research: partial };
        const next = { ...runtime.state, draft, stage: "research" };
        if (deps.emitMode === "ag-ui") await dispatchCustomEvent("manually_emit_state", next, runtime.config);
        if (deps.emitMode === "copilotkit") await copilotkitEmitState(runtime.config, next);
      }
      const result = ResearchSchema.parse(final);
      return new Command({
        update: {
          research: result,
          topic,
          stage: "research",
          draft: null,
          messages: [
            new ToolMessage({
              content: JSON.stringify({ ok: true, title: result.title }),
              tool_call_id: runtime.toolCallId,
              name: "research",
            }),
          ],
        },
      });
    },
    { name: "research", description: "Research a topic", schema: z.object({ topic: z.string() }) },
  );

  const renderSurface = tool(
    async ({ target, title, components }, runtime: any) => {
      const { valid, errors } = validateA2UIComponents({
        components,
        catalog: CHAT_CATALOG as any,
        validateBindings: false,
      });
      if (!valid) return JSON.stringify({ error: formatValidationErrors(errors) });
      const surfaceId = `chat-${uuidv4()}`;
      if (target === "chat") {
        return JSON.stringify({
          [A2UI_OPERATIONS_KEY]: assembleOps({ intent: "create", surfaceId, catalogId: CHAT_CATALOG_ID, components }),
        });
      }
      return new Command({
        update: {
          board: [...(runtime.state.board ?? []), { id: surfaceId, title }],
          messages: [new ToolMessage({ content: JSON.stringify({ ok: true, surfaceId }), tool_call_id: runtime.toolCallId, name: "renderSurface" })],
        },
      });
    },
    { name: "renderSurface", description: "Render a surface", schema: RenderSurfaceArgsSchema as any },
  );

  /** S5/S8: reports what reached the tool through context and config. */
  const whoami = tool(
    async (_args, runtime: any) =>
      JSON.stringify({
        context: { ...runtime.context, apiKey: runtime.context?.apiKey ? "<present>" : undefined },
        configurableKeys: Object.keys(runtime.config?.configurable ?? {}),
        forwardedHeaders: Object.keys(runtime.config?.configurable?.copilotkit_forwarded_headers ?? {}),
        stateKeys: Object.keys(runtime.state ?? {}),
        agUi: runtime.state?.["ag-ui"] ? Object.keys(runtime.state["ag-ui"]) : null,
      }),
    { name: "whoami", description: "debug", schema: z.object({}) },
  );

  return createAgent({
    model: deps.model,
    tools: [research, renderSurface, whoami, ...(deps.extraTools ?? [])],
    systemPrompt: "You are the learning supervisor.",
    stateSchema: StateSchema as any,
    contextSchema: ContextSchema as any,
    middleware: [copilotkitMiddleware, contextBuilder(deps.seen), ...(deps.extraMiddleware ?? [])] as any,
    checkpointer: deps.checkpointer,
  });
};
