import { generateText, Output } from "ai";
import type { z } from "zod";

import { OPENAI_CALL_OPTIONS } from "@/constants/openai";
import { createLanguageModel } from "@/services/llm/language-model";
import type { RunSettings } from "@/types/llm";

interface GenerateStructuredParams<T extends z.ZodType> {
  settings: RunSettings;
  system: string;
  prompt: string;
  schema: T;
  signal?: AbortSignal;
}

/**
 * One structured-output call to the OpenAI model. Every subagent is one of these. (`generateText` + `Output.object`
 * is the AI SDK 6 replacement for the deprecated `generateObject`.)
 */
export const generateStructured = async <T extends z.ZodType>({
  settings,
  system,
  prompt,
  schema,
  signal,
}: GenerateStructuredParams<T>): Promise<z.infer<T>> => {
  const { output } = await generateText({
    model: createLanguageModel(settings.apiKey),
    providerOptions: OPENAI_CALL_OPTIONS,
    system,
    prompt,
    output: Output.object({ schema }),
    abortSignal: signal,
  });
  // The SDK already validated `output`; parsing again gives it the schema's
  // type, which the generic call cannot infer.
  return schema.parse(output);
};
