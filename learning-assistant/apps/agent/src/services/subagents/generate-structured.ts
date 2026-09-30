import { HumanMessage, SystemMessage } from "@langchain/core/messages";
import { parsePartialJson } from "@langchain/core/output_parsers";
import { toJsonSchema } from "@langchain/core/utils/json_schema";
import type { z } from "zod";

import {
  SILENT_RUN_METADATA,
  STRUCTURED_OUTPUT_NAME,
} from "../../constants/openai";
import type { DeepPartial, RunSettings } from "../../types/llm";
import { createChatModel } from "../llm/chat-model";

interface GenerateStructuredParams<T extends z.ZodType> {
  settings: RunSettings;
  system: string;
  prompt: string;
  schema: T;
  signal?: AbortSignal;
  /** Streams the output: called with each partial object as it grows. */
  onPartial?: (partial: DeepPartial<z.infer<T>>) => void;
}

/** The request option that makes the model answer in `schema`'s JSON. */
const toResponseFormat = (schema: z.ZodType) => ({
  type: "json_schema" as const,
  json_schema: {
    name: STRUCTURED_OUTPUT_NAME,
    strict: true,
    schema: { ...toJsonSchema(schema), additionalProperties: false },
  },
});

/**
 * One structured-output call to the OpenAI model. Every subagent is one of
 * these. The reply is streamed as raw JSON text and parsed as it grows,
 * because `withStructuredOutput` yields only the finished object; with
 * `onPartial` each parse is reported. The whole reply is then validated
 * against `schema`. A failed or stopped (`signal`) call throws the
 * provider's own error. The call is marked silent, so inside a tool its
 * tokens stay out of the chat.
 */
export const generateStructured = async <T extends z.ZodType>({
  settings,
  system,
  prompt,
  schema,
  signal,
  onPartial,
}: GenerateStructuredParams<T>): Promise<z.infer<T>> => {
  const stream = await createChatModel(settings.apiKey).stream(
    [new SystemMessage(system), new HumanMessage(prompt)],
    {
      signal,
      metadata: SILENT_RUN_METADATA,
      response_format: toResponseFormat(schema),
    },
  );

  let text = "";
  for await (const chunk of stream) {
    if (!chunk.text) {
      continue;
    }
    text += chunk.text;
    const partial: unknown = onPartial ? parsePartialJson(text) : null;
    if (partial !== null && typeof partial === "object") {
      onPartial?.(partial as DeepPartial<z.infer<T>>);
    }
  }

  // `JSON.parse`, not the partial parser: a reply cut short must fail here
  // rather than pass as a shorter, valid-looking object.
  return schema.parse(JSON.parse(text));
};
