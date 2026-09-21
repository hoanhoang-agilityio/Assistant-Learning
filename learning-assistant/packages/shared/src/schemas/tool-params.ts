import { z } from "zod";

import { QUESTION_COUNT } from "./settings";
import type { SubagentTool } from "./tool-results";

/**
 * The arguments the Supervisor LLM sends to each subagent tool. The server
 * tools and the chat's progress cards both read these, so an argument is
 * spelled once.
 */
export const ToolParamSchemas = {
  research: z.object({
    topic: z.string().min(1).describe("Short noun phrase for the topic"),
  }),
  makeNotes: z.object({}),
  simplify: z.object({
    scope: z
      .enum(["all", "selection"])
      .describe("Simplify the whole set of notes or only the selected text"),
    selection: z
      .string()
      .min(1)
      .optional()
      .describe("The selected text, exactly as it appears; only for selection"),
  }),
  generateQuiz: z.object({
    count: z
      .int()
      .min(QUESTION_COUNT.min)
      .max(QUESTION_COUNT.max)
      .optional()
      .describe("Number of questions; defaults to the user's setting"),
  }),
  evaluate: z.object({}),
} as const satisfies Record<SubagentTool, z.ZodType>;

export type ToolParams<T extends SubagentTool> = z.infer<
  (typeof ToolParamSchemas)[T]
>;
