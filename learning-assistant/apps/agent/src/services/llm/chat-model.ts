import type { CallbackManagerForLLMRun } from "@langchain/core/callbacks/manager";
import type { BaseMessage } from "@langchain/core/messages";
import type { ChatGenerationChunk } from "@langchain/core/outputs";
import { ChatOpenAIResponses } from "@langchain/openai";

import { OPENAI_MODEL, OPENAI_REASONING } from "../../constants/openai";

/**
 * Gives every chunk of a reply the id of the first chunk that has one. Only
 * the Responses API's first and last events carry the response id, so every
 * chunk in between would be named after the LangChain run instead.
 */
export async function* withResponseId(
  chunks: AsyncIterable<ChatGenerationChunk>,
): AsyncGenerator<ChatGenerationChunk> {
  let id: string | undefined;
  for await (const chunk of chunks) {
    id ??= chunk.message.id;
    if (chunk.message.id == null && id) {
      chunk.message.id = id;
    }
    yield chunk;
  }
}

/**
 * The Responses API model whose streamed chunks carry the id the saved
 * message gets.
 * The AG-UI adapter names a streaming message by its chunks' id, and the
 * browser swaps it for the saved one at the end of the run: with two ids,
 * the reply moves below anything drawn after it, such as a chat surface.
 * The chunk is stamped before the model reports it, since it reports a
 * chunk only once the next one is asked for. `ChatOpenAI` cannot be
 * extended for this: it hands Responses calls to an inner model of its own.
 */
class StableIdChatOpenAI extends ChatOpenAIResponses {
  async *_streamResponseChunks(
    messages: BaseMessage[],
    options: this["ParsedCallOptions"],
    runManager?: CallbackManagerForLLMRun,
  ): AsyncGenerator<ChatGenerationChunk> {
    yield* withResponseId(
      super._streamResponseChunks(messages, options, runManager),
    );
  }
}

/**
 * The OpenAI model on LangChain, called with the user's own key; the key is
 * never read from env. It lives only inside this instance: run `context` and
 * `configurable` are recorded in traces, a model's key is not. The Responses
 * API is required for tools together with reasoning.
 */
export const createChatModel = (apiKey: string): ChatOpenAIResponses =>
  new StableIdChatOpenAI({
    model: OPENAI_MODEL,
    apiKey,
    reasoning: OPENAI_REASONING,
  });
