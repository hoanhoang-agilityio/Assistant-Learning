import { ChatOpenAI } from "@langchain/openai";

import { OPENAI_MODEL, OPENAI_REASONING } from "../../constants/openai";

/**
 * The OpenAI model on LangChain, called with the user's own key; the key is
 * never read from env. It lives only inside this instance: run `context` and
 * `configurable` are recorded in traces, a model's key is not. The Responses
 * API is required for tools together with reasoning.
 */
export const createChatModel = (apiKey: string): ChatOpenAI =>
  new ChatOpenAI({
    model: OPENAI_MODEL,
    apiKey,
    reasoning: OPENAI_REASONING,
    useResponsesApi: true,
  });
