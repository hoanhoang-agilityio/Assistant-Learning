import { createOpenAI } from "@ai-sdk/openai";
import { type LanguageModel, wrapLanguageModel } from "ai";

import { OPENAI_MODEL } from "@/constants/openai";
import { langSmithTracing } from "@/services/llm/langsmith-tracing";

/**
 * The OpenAI model, called with the user's own key; the key is never read from
 * env. Each call is traced to LangSmith as `name` when `LANGSMITH_TRACING` is
 * `true`.
 */
export const createLanguageModel = (
  apiKey: string,
  name = OPENAI_MODEL,
): LanguageModel =>
  wrapLanguageModel({
    model: createOpenAI({ apiKey })(OPENAI_MODEL),
    middleware: langSmithTracing(name, OPENAI_MODEL),
  });
