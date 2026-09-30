import { CallbackManagerForLLMRun } from "@langchain/core/callbacks/manager";
import {
  BaseChatModel,
  type BaseChatModelCallOptions,
} from "@langchain/core/language_models/chat_models";
import {
  AIMessage,
  AIMessageChunk,
  type BaseMessage,
} from "@langchain/core/messages";
import { ChatGenerationChunk, type ChatResult } from "@langchain/core/outputs";

export interface Turn {
  text?: string;
  toolCalls?: { name: string; args: unknown; id?: string }[];
}

/**
 * A scripted chat model: each call pops the next Turn (or asks `pick`). Tool
 * call args stream in small pieces so TOOL_CALL_ARGS deltas are observable.
 * Records exactly what messages each call received.
 */
export class ScriptedModel extends BaseChatModel<BaseChatModelCallOptions> {
  calls: BaseMessage[][] = [];
  boundTools: string[] = [];
  constructor(private pick: (messages: BaseMessage[], n: number) => Turn) {
    super({});
  }
  _llmType() {
    return "scripted";
  }
  bindTools(tools: any[]): any {
    this.boundTools = tools.map((t) => t.name ?? t.function?.name);
    return this;
  }
  private turn(messages: BaseMessage[]) {
    this.calls.push(messages);
    return this.pick(messages, this.calls.length - 1);
  }
  async _generate(messages: BaseMessage[]): Promise<ChatResult> {
    const t = this.turn(messages);
    const message = new AIMessage({
      content: t.text ?? "",
      tool_calls: (t.toolCalls ?? []).map((c, i) => ({
        id: c.id ?? `call_${this.calls.length}_${i}`,
        name: c.name,
        args: c.args as Record<string, unknown>,
        type: "tool_call" as const,
      })),
    });
    return { generations: [{ text: String(message.content), message }] };
  }
  async *_streamResponseChunks(
    messages: BaseMessage[],
    _options: this["ParsedCallOptions"],
    runManager?: CallbackManagerForLLMRun,
  ): AsyncGenerator<ChatGenerationChunk> {
    const t = this.turn(messages);
    const id = `msg_${Date.now()}_${this.calls.length}`;
    const emit = async (chunk: AIMessageChunk, text = "") => {
      const gen = new ChatGenerationChunk({ text, message: chunk });
      yield_.push(gen);
      await runManager?.handleLLMNewToken(text, undefined, undefined, undefined, undefined, { chunk: gen });
    };
    const yield_: ChatGenerationChunk[] = [];
    for (const piece of (t.text ?? "").match(/.{1,8}/gs) ?? []) {
      await emit(new AIMessageChunk({ id, content: piece }), piece);
      yield* yield_.splice(0);
    }
    for (const [i, c] of (t.toolCalls ?? []).entries()) {
      const callId = c.id ?? `call_${this.calls.length}_${i}`;
      const json = JSON.stringify(c.args);
      const parts = json.match(/.{1,24}/gs) ?? [""];
      for (const [j, part] of parts.entries()) {
        await emit(
          new AIMessageChunk({
            id,
            content: "",
            tool_call_chunks: [
              { index: i, id: j === 0 ? callId : undefined, name: j === 0 ? c.name : undefined, args: part, type: "tool_call_chunk" },
            ],
          }),
        );
        yield* yield_.splice(0);
      }
    }
    await emit(new AIMessageChunk({ id, content: "", response_metadata: { finish_reason: t.toolCalls?.length ? "tool_calls" : "stop" } }));
    yield* yield_.splice(0);
  }
}
