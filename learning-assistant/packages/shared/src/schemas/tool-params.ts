import { z } from "zod";

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
  // The question count comes from the user's settings only, so the model
  // cannot override it (it tends to repeat the count of an earlier quiz).
  generateQuiz: z.object({}),
  evaluate: z.object({}),
} as const satisfies Record<SubagentTool, z.ZodType>;

export type ToolParams<T extends SubagentTool> = z.infer<
  (typeof ToolParamSchemas)[T]
>;

/** Arguments of the `confirmNewTopic` human-in-the-loop tool. */
export const ConfirmNewTopicParamsSchema = z.object({
  topic: z
    .string()
    .min(1)
    .describe("Short noun phrase for the new topic the student asked about"),
});

/** What the student chose on the new-topic card. */
export const NewTopicDecisionSchema = z.object({
  confirmed: z.boolean(),
  /** What the Supervisor should do next. */
  instruction: z.string(),
});

export type ConfirmNewTopicParams = z.infer<typeof ConfirmNewTopicParamsSchema>;
export type NewTopicDecision = z.infer<typeof NewTopicDecisionSchema>;
