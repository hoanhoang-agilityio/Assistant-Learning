import type { Settings } from "@repo/shared/schemas";
import { generateText, Output } from "ai";
import type { z } from "zod";

import { createLanguageModel } from "@/services/llm/language-model";
import { getReasoningOptions } from "@/services/llm/reasoning";

interface GenerateStructuredParams<T extends z.ZodType> {
  settings: Settings;
  system: string;
  prompt: string;
  schema: T;
  signal?: AbortSignal;
}

/**
 * One structured-output call with the model and reasoning effort from
 * Settings. Every subagent is one of these. (`generateText` + `Output.object`
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
    model: createLanguageModel(settings.provider, settings.model),
    providerOptions: getReasoningOptions(
      settings.provider,
      settings.model,
      settings.reasoningEffort,
    ),
    system,
    prompt,
    output: Output.object({ schema }),
    abortSignal: signal,
  });
  // The SDK already validated `output`; parsing again gives it the schema's
  // type, which the generic call cannot infer.
  return schema.parse(output);
};
