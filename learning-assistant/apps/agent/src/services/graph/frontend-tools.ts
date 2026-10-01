import { AIMessage, type ToolCall } from "@langchain/core/messages";
import { createMiddleware } from "langchain";
import { z } from "zod";

import { FRONTEND_TOOLS_INPUT_KEY } from "../../constants/graph";

/**
 * What the AG-UI adapter writes under `copilotkit`: the run's frontend tools
 * (`actions`, OpenAI function definitions). The middleware adds where it
 * parks the model's calls to them until the run ends.
 */
const FrontendToolsSchema = z
  .object({
    actions: z.array(z.unknown()).default([]),
    interceptedToolCalls: z.array(z.custom<ToolCall>()).optional(),
    originalAIMessageId: z.string().optional(),
  })
  .loose();

const FrontendToolsStateSchema = z.object({
  [FRONTEND_TOOLS_INPUT_KEY]: FrontendToolsSchema.optional(),
});

type FrontendToolsState = z.infer<typeof FrontendToolsSchema>;

/** A frontend tool's name, in either shape the browser sends it. */
const getToolName = (tool: unknown): string | undefined => {
  const { name, function: fn } = (tool ?? {}) as {
    name?: unknown;
    function?: { name?: unknown };
  };
  const toolName = fn?.name ?? name;
  return typeof toolName === "string" ? toolName : undefined;
};

/**
 * The message with `toolCalls` as its tool calls and everything else kept.
 * With v1 content blocks the old tool-call blocks are dropped first, or
 * `AIMessage` would merge them back in.
 */
const withToolCalls = (message: AIMessage, toolCalls: ToolCall[]): AIMessage =>
  new AIMessage({
    content:
      message.response_metadata?.output_version === "v1" &&
      Array.isArray(message.content)
        ? message.content.filter(
            (block) =>
              block.type !== "tool_call" && block.type !== "tool_call_chunk",
          )
        : message.content,
    additional_kwargs: message.additional_kwargs,
    response_metadata: message.response_metadata,
    tool_calls: toolCalls,
    invalid_tool_calls: message.invalid_tool_calls,
    usage_metadata: message.usage_metadata,
    id: message.id,
    name: message.name,
  });

/**
 * Lets the Supervisor call the browser's frontend tools (theme, layout,
 * settings, chat cards). Replaces `@copilotkit/sdk-js`'s deprecated
 * `copilotkitMiddleware`, keeping only what this app used of it:
 * - each model call is offered the run's frontend tools next to its own;
 * - after a model call, its calls to frontend tools are taken out of the
 *   message, so the agent does not try to run them and the run ends once
 *   no server tool is left to run;
 * - when the run ends they are put back, so the saved message holds them
 *   and the browser's results answer them in the next run.
 */
export const frontendToolsMiddleware = createMiddleware({
  name: "FrontendTools",
  stateSchema: FrontendToolsStateSchema,
  wrapModelCall: (request, handler) => {
    const actions = request.state[FRONTEND_TOOLS_INPUT_KEY]?.actions ?? [];
    if (actions.length === 0) {
      return handler(request);
    }

    return handler({
      ...request,
      tools: [
        ...request.tools,
        ...(actions as (typeof request.tools)[number][]),
      ],
    });
  },
  afterModel: (state) => {
    const frontendTools = state[FRONTEND_TOOLS_INPUT_KEY];
    const actions = frontendTools?.actions ?? [];
    const names = new Set(actions.map(getToolName).filter(Boolean));
    const last = state.messages.at(-1);
    if (
      names.size === 0 ||
      !last ||
      !AIMessage.isInstance(last) ||
      !last.tool_calls?.length
    ) {
      return;
    }

    const frontendCalls = last.tool_calls.filter(({ name }) => names.has(name));
    if (frontendCalls.length === 0) {
      return;
    }
    const serverCalls = last.tool_calls.filter(({ name }) => !names.has(name));
    return {
      messages: [
        ...state.messages.slice(0, -1),
        withToolCalls(last, serverCalls),
      ],
      [FRONTEND_TOOLS_INPUT_KEY]: {
        ...frontendTools,
        actions,
        interceptedToolCalls: frontendCalls,
        originalAIMessageId: last.id,
      } satisfies FrontendToolsState,
    };
  },
  afterAgent: (state) => {
    const frontendTools = state[FRONTEND_TOOLS_INPUT_KEY];
    const intercepted = frontendTools?.interceptedToolCalls;
    const messageId = frontendTools?.originalAIMessageId;
    if (!frontendTools || !intercepted?.length || !messageId) {
      return;
    }

    return {
      messages: state.messages.map((message) =>
        AIMessage.isInstance(message) && message.id === messageId
          ? withToolCalls(message, [
              ...(message.tool_calls ?? []),
              ...intercepted,
            ])
          : message,
      ),
      [FRONTEND_TOOLS_INPUT_KEY]: {
        ...frontendTools,
        interceptedToolCalls: undefined,
        originalAIMessageId: undefined,
      } satisfies FrontendToolsState,
    };
  },
});
