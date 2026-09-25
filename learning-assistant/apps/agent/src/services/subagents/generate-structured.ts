import { type DeepPartial, generateText, Output, streamText } from "ai";
import type { z } from "zod";

import { OPENAI_CALL_OPTIONS } from "../../constants/openai";
import type { RunSettings } from "../../types/llm";
import { createLanguageModel } from "../llm/language-model";

interface GenerateStructuredParams<T extends z.ZodType> {
  settings: RunSettings;
  system: string;
  prompt: string;
  schema: T;
  signal?: AbortSignal;
  /** Streams the output: called with each partial object as it grows. */
  onPartial?: (partial: DeepPartial<z.infer<T>>) => void;
}

/**
 * Streams the output, reporting each partial object, and returns the
 * validated whole. A failed stream throws the provider's own error (a bad
 * key, a rate limit…) rather than the SDK's generic "no output".
 */
const streamStructured = async <T extends z.ZodType>(
  { settings, system, prompt, schema, signal }: GenerateStructuredParams<T>,
  onPartial: (partial: DeepPartial<z.infer<T>>) => void,
): Promise<unknown> => {
  let streamError: unknown;
  const result = streamText({
    model: createLanguageModel(settings.apiKey),
    providerOptions: OPENAI_CALL_OPTIONS,
    system,
    prompt,
    output: Output.object({ schema }),
    abortSignal: signal,
    onError: ({ error }) => {
      streamError = error;
    },
  });
  try {
    for await (const partial of result.partialOutputStream) {
      onPartial(partial as DeepPartial<z.infer<T>>);
    }
    return await result.output;
  } catch (error) {
    throw streamError ?? error;
  }
};

/**
 * One structured-output call to the OpenAI model. Every subagent is one of
 * these; with `onPartial` it streams. (`generateText` + `Output.object` is
 * the AI SDK 6 replacement for the deprecated `generateObject`.)
 */
export const generateStructured = async <T extends z.ZodType>(
  params: GenerateStructuredParams<T>,
): Promise<z.infer<T>> => {
  const { settings, system, prompt, schema, signal, onPartial } = params;
  const output = onPartial
    ? await streamStructured(params, onPartial)
    : (
        await generateText({
          model: createLanguageModel(settings.apiKey),
          providerOptions: OPENAI_CALL_OPTIONS,
          system,
          prompt,
          output: Output.object({ schema }),
          abortSignal: signal,
        })
      ).output;
  // The SDK already validated `output`; parsing again gives it the schema's
  // type, which the generic call cannot infer.
  return schema.parse(output);
};
