import type { CallbackManagerForLLMRun } from "@langchain/core/callbacks/manager";
import { BaseChatModel } from "@langchain/core/language_models/chat_models";
import {
  AIMessage,
  AIMessageChunk,
  type BaseMessage,
} from "@langchain/core/messages";
import { ChatGenerationChunk, type ChatResult } from "@langchain/core/outputs";
import { v4 as uuidv4 } from "uuid";

interface FixedToolCall {
  name: string;
  args: Record<string, unknown>;
}

/**
 * A chat model that does not think: whatever it is asked, it answers with
 * one fixed tool call. It stands in for the Supervisor's model when code,
 * not the model, decides what happens next (the quiz Submit button), so the
 * call still streams to the chat and runs through the graph like any other.
 * The name and the arguments go in separate chunks, as OpenAI sends them;
 * the AG-UI adapter drops arguments that arrive with the name.
 */
export class ToolCallModel extends BaseChatModel {
  private call: FixedToolCall;

  constructor(call: FixedToolCall) {
    super({});
    this.call = call;
  }

  _llmType(): string {
    return "tool-call";
  }

  bindTools(): this {
    return this;
  }

  async _generate(): Promise<ChatResult> {
    const message = new AIMessage({
      content: "",
      tool_calls: [{ ...this.call, id: uuidv4(), type: "tool_call" }],
    });
    return { generations: [{ text: "", message }] };
  }

  async *_streamResponseChunks(
    _messages: BaseMessage[],
    _options: this["ParsedCallOptions"],
    runManager?: CallbackManagerForLLMRun,
  ): AsyncGenerator<ChatGenerationChunk> {
    const id = uuidv4();
    const toolCall = { index: 0, type: "tool_call_chunk" as const };
    const messages = [
      new AIMessageChunk({
        id,
        content: "",
        tool_call_chunks: [
          { ...toolCall, id: uuidv4(), name: this.call.name, args: "" },
        ],
      }),
      new AIMessageChunk({
        id,
        content: "",
        tool_call_chunks: [
          { ...toolCall, args: JSON.stringify(this.call.args) },
        ],
      }),
      new AIMessageChunk({
        id,
        content: "",
        response_metadata: { finish_reason: "tool_calls" },
      }),
    ];

    for (const message of messages) {
      const chunk = new ChatGenerationChunk({ text: "", message });
      await runManager?.handleLLMNewToken(
        "",
        undefined,
        undefined,
        undefined,
        undefined,
        { chunk },
      );
      yield chunk;
    }
  }
}
