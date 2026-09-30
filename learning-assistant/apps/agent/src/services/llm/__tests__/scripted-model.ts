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
  text?: string;
  toolCalls?: { name: string; args: Record<string, unknown>; id?: string }[];
}

/** One call the model received. */
export interface ScriptedCall {
  messages: BaseMessage[];
  options: BaseChatModelCallOptions;
}

const TEXT_PIECE = /.{1,8}/gs;
const ARGS_PIECE = /.{1,24}/gs;

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

  constructor(
    private script: (messages: BaseMessage[], call: number) => ScriptedTurn,
  ) {
    super({});
  }

  _llmType(): string {
    return "scripted";
  }

  bindTools(tools: BindToolsInput[]): this {
    this.boundTools = tools.map(toToolName);
    return this;
  }

  private next(
    messages: BaseMessage[],
    options: BaseChatModelCallOptions,
  ): ScriptedTurn {
    this.calls.push({ messages, options });
    return this.script(messages, this.calls.length - 1);
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
