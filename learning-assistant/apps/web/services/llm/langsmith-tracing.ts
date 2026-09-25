import type { LanguageModelMiddleware } from "ai";
import { traceable } from "langsmith/traceable";

type Middleware = Required<LanguageModelMiddleware>;
type CallParams = Parameters<Middleware["wrapStream"]>[0]["params"];
type GenerateResult = Awaited<
  ReturnType<Parameters<Middleware["wrapGenerate"]>[0]["doGenerate"]>
>;
type StreamResult = Awaited<
  ReturnType<Parameters<Middleware["wrapStream"]>[0]["doStream"]>
>;
type StreamPart =
  StreamResult["stream"] extends ReadableStream<infer Part> ? Part : never;
type ToolCallPart = Extract<StreamPart, { type: "tool-call" }>;
type Usage = GenerateResult["usage"];

/** One model call: the params are what is traced, `call` is what runs. */
interface TracedCall<Result> {
  params: CallParams;
  call: () => PromiseLike<Result>;
}

const run = async <Result>({ call }: TracedCall<Result>) => call();

const toInputs = ({ params }: Readonly<TracedCall<unknown>>) => ({
  messages: params.prompt,
  tools: params.tools?.map(({ name }) => name),
});

/** The call's result as an assistant message, the shape LangSmith renders. */
const toOutputs = (text: string, toolCalls: ToolCallPart[], usage?: Usage) => {
  const inputTokens = usage?.inputTokens.total ?? 0;
  const outputTokens = usage?.outputTokens.total ?? 0;
  // Cached input is served faster; reasoning is output the student never
  // sees but waits for before the first visible token.
  return {
    role: "assistant",
    content: text,
    tool_calls: toolCalls.map(({ toolCallId, toolName, input }) => ({
      id: toolCallId,
      type: "function",
      function: { name: toolName, arguments: input },
    })),
    usage_metadata: {
      input_tokens: inputTokens,
      output_tokens: outputTokens,
      total_tokens: inputTokens + outputTokens,
      input_token_details: { cache_read: usage?.inputTokens.cacheRead ?? 0 },
      output_token_details: {
        reasoning: usage?.outputTokens.reasoning ?? 0,
      },
    },
  };
};

const summarizeGenerate = ({ content, usage }: Readonly<GenerateResult>) =>
  toOutputs(
    content
      .flatMap((part) => (part.type === "text" ? [part.text] : []))
      .join(""),
    content.filter((part): part is ToolCallPart => part.type === "tool-call"),
    usage,
  );

const summarizeStream = (parts: StreamPart[]) => {
  let text = "";
  const toolCalls: ToolCallPart[] = [];
  let usage: Usage | undefined;
  for (const part of parts) {
    if (part.type === "text-delta") {
      text += part.delta;
    } else if (part.type === "tool-call") {
      toolCalls.push(part);
    } else if (part.type === "finish") {
      usage = part.usage;
    }
  }
  return toOutputs(text, toolCalls, usage);
};

/**
 * Traces each model call to LangSmith as an `llm` run named `name`, nested
 * under the current `traceable` span if there is one. A no-op unless
 * `LANGSMITH_TRACING` is `true`. Streams are traced once they finish, so the
 * run holds the whole reply and its token usage.
 */
export const langSmithTracing = (
  name: string,
  modelId: string,
): LanguageModelMiddleware => {
  const config = {
    name,
    run_type: "llm",
    metadata: { ls_provider: "openai", ls_model_name: modelId },
    processInputs: toInputs,
  };
  return {
    specificationVersion: "v3",
    wrapGenerate: ({ doGenerate, params }) =>
      traceable(run<GenerateResult>, {
        ...config,
        processOutputs: summarizeGenerate,
      })({ params, call: doGenerate }),
    wrapStream: ({ doStream, params }) =>
      traceable(run<StreamResult>, {
        ...config,
        __finalTracedIteratorKey: "stream",
        aggregator: summarizeStream,
      })({ params, call: doStream }),
  };
};
