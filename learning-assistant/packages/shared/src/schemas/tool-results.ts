import { z } from "zod";

import {
  EvaluationSchema,
  FeedbackSchema,
  QuizSchema,
  ScoreSchema,
} from "./learning-state";
import { ResearchResultSchema } from "./research";

/** Supervisor tools that run a subagent and write its result to state. */
export const SUBAGENT_TOOLS = [
  "research",
  "makeMaterial",
  "simplify",
  "generateQuiz",
  "evaluate",
] as const;

export const SubagentToolSchema = z.enum(SUBAGENT_TOOLS);

const FailureSchema = z.object({
  ok: z.literal(false),
  error: z.string().min(1),
});

const createResultSchema = <T extends z.ZodType>(data: T) =>
  z.discriminatedUnion("ok", [
    z.object({ ok: z.literal(true), data }),
    FailureSchema,
  ]);

const MarkdownSchema = z.string().min(1);

/**
 * What each subagent tool returns. Tools never throw: a failure comes back as
 * `{ ok: false, error }` so the wrapper can set `status.error`.
 */
export const ToolResultSchemas = {
  research: createResultSchema(
    z.object({ topic: z.string().min(1), research: ResearchResultSchema }),
  ),
  makeMaterial: createResultSchema(z.object({ markdown: MarkdownSchema })),
  simplify: createResultSchema(
    z.discriminatedUnion("scope", [
      z.object({ scope: z.literal("all"), markdown: MarkdownSchema }),
      z.object({
        scope: z.literal("selection"),
        /** The selected text, exactly as it appears in the active view. */
        selection: z.string().min(1),
        markdown: MarkdownSchema,
      }),
    ]),
  ),
  generateQuiz: createResultSchema(z.object({ quiz: QuizSchema })),
  evaluate: createResultSchema(
    z.object({
      /** The answers that were graded; they replace `quiz.answers`. */
      answers: QuizSchema.shape.answers,
      evaluation: EvaluationSchema,
      score: ScoreSchema,
      feedback: FeedbackSchema,
    }),
  ),
} as const satisfies Record<SubagentTool, z.ZodType>;

export type SubagentTool = z.infer<typeof SubagentToolSchema>;
export type ToolResult<T extends SubagentTool> = z.infer<
  (typeof ToolResultSchemas)[T]
>;
/** The `data` of a successful result. */
export type ToolResultData<T extends SubagentTool> = Extract<
  ToolResult<T>,
  { ok: true }
>["data"];
