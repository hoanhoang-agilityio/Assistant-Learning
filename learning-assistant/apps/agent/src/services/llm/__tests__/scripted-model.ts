import type { CallbackManagerForLLMRun } from "@langchain/core/callbacks/manager";
import {
  BaseChatModel,
  type BaseChatModelCallOptions,
  type BindToolsInput,
} from "@langchain/core/language_models/chat_models";
import {
  AIMessage,
  AIMessageChunk,
  type BaseMessage,
} from "@langchain/core/messages";
import { ChatGenerationChunk, type ChatResult } from "@langchain/core/outputs";

/** What the model answers on one call: text, tool calls, or both. */
export interface ScriptedTurn {
  /** Wait this long before answering; a stopped run ends the wait. */
  delayMs?: number;
  text?: string;
  toolCalls?: { name: string; args: Record<string, unknown>; id?: string }[];
}

/** One call the model received. */
export interface ScriptedCall {
  messages: BaseMessage[];
  options: BaseChatModelCallOptions;
  /** The names of the tools bound to the model when it was called. */
  tools: string[];
  /** How many calls this model had answered before this one. */
  index: number;
}

/** Decides what the model answers to one call. */
export type Script = (
  messages: BaseMessage[],
  call: ScriptedCall,
) => ScriptedTurn;

const TEXT_PIECE = /.{1,8}/gs;
const ARGS_PIECE = /.{1,24}/gs;

/** Resolves after `ms`, or rejects as soon as `signal` is aborted. */
const waitFor = (ms: number, signal?: AbortSignal): Promise<void> =>
  new Promise((resolve, reject) => {
    if (ms === 0) {
      resolve();
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new Error("This operation was aborted"));
    });
  });

const toToolName = (tool: BindToolsInput): string => {
  if ("name" in tool && typeof tool.name === "string") {
    return tool.name;
  }
  const { function: fn } = tool as { function?: { name?: string } };
  return fn?.name ?? "";
};

/**
 * A chat model for tests: each call answers with what `script` returns for
 * the messages it was given, streamed in small pieces, and is recorded in
 * `calls`. A tool call's name and its arguments go in separate chunks, as
 * OpenAI sends them; the AG-UI adapter drops arguments that arrive with the
 * name.
 */
export class ScriptedModel extends BaseChatModel {
  calls: ScriptedCall[] = [];
  boundTools: string[] = [];
  /** The options of the last `bindTools` call, e.g. `tool_choice`. */
  boundOptions: Record<string, unknown> = {};

  private script: Script;

  constructor(script: Script) {
    super({});
    this.script = script;
  }

  _llmType(): string {
    return "scripted";
  }

  bindTools(
    tools: BindToolsInput[],
    options: Record<string, unknown> = {},
  ): this {
    this.boundTools = tools.map(toToolName);
    this.boundOptions = options;
    return this;
  }

  private next(
    messages: BaseMessage[],
    options: BaseChatModelCallOptions,
  ): ScriptedTurn {
    const call: ScriptedCall = {
      messages,
      options,
      tools: this.boundTools,
      index: this.calls.length,
    };
    this.calls.push(call);
    return this.script(messages, call);
  }

  async _generate(
    messages: BaseMessage[],
    options: this["ParsedCallOptions"],
  ): Promise<ChatResult> {
    const turn = this.next(messages, options);
    const message = new AIMessage({
      content: turn.text ?? "",
      tool_calls: (turn.toolCalls ?? []).map((call, index) => ({
        id: call.id ?? `call_${this.calls.length}_${index}`,
        name: call.name,
        args: call.args,
        type: "tool_call" as const,
      })),
    });
    return { generations: [{ text: message.text, message }] };
  }

  async *_streamResponseChunks(
    messages: BaseMessage[],
    options: this["ParsedCallOptions"],
    runManager?: CallbackManagerForLLMRun,
  ): AsyncGenerator<ChatGenerationChunk> {
    const turn = this.next(messages, options);
    await waitFor(turn.delayMs ?? 0, options.signal);
    const id = `msg_${this.calls.length}_${Date.now()}`;
    const toChunk = async (message: AIMessageChunk, text = "") => {
      const chunk = new ChatGenerationChunk({ text, message });
      await runManager?.handleLLMNewToken(
        text,
        undefined,
        undefined,
        undefined,
        undefined,
        { chunk },
      );
      return chunk;
    };

    for (const piece of (turn.text ?? "").match(TEXT_PIECE) ?? []) {
      yield toChunk(new AIMessageChunk({ id, content: piece }), piece);
    }

    for (const [index, call] of (turn.toolCalls ?? []).entries()) {
      const toolCallChunk = { index, type: "tool_call_chunk" as const };
      yield toChunk(
        new AIMessageChunk({
          id,
          content: "",
          tool_call_chunks: [
            {
              ...toolCallChunk,
              id: call.id ?? `call_${this.calls.length}_${index}`,
              name: call.name,
              args: "",
            },
          ],
        }),
      );
      for (const args of JSON.stringify(call.args).match(ARGS_PIECE) ?? []) {
        yield toChunk(
          new AIMessageChunk({
            id,
            content: "",
            tool_call_chunks: [{ ...toolCallChunk, args }],
          }),
        );
      }
    }

    yield toChunk(
      new AIMessageChunk({
        id,
        content: "",
        response_metadata: {
          finish_reason: turn.toolCalls?.length ? "tool_calls" : "stop",
        },
      }),
    );
  }
}
