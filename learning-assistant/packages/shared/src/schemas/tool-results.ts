import { z } from "zod";

import { NEW_CONVERSATION_REQUIREMENT } from "../constants/agents";
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
 * `research` refused to replace existing learning material or a quiz. Not a
 * failure: nothing changed, and `instruction` tells the Supervisor to point
 * the student to "New topic", which starts a new conversation.
 */
export const NewConversationRequiredSchema = z.object({
  ok: z.literal(false),
  requires: z.literal(NEW_CONVERSATION_REQUIREMENT),
  topic: z.string().min(1),
  instruction: z.string().min(1),
});

/**
 * What each subagent tool returns. Tools never throw: a failure comes back as
 * `{ ok: false, error }` so the wrapper can set `status.error`. `research`
 * can also refuse a second topic in one conversation.
 */
export const ToolResultSchemas = {
  research: z.union([
    createResultSchema(
      z.object({ topic: z.string().min(1), research: ResearchResultSchema }),
    ),
    NewConversationRequiredSchema,
  ]),
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

/**
 * What each subagent tool tells the Supervisor and its chat card once it has
 * run on the LangChain graph: whether it worked, and a few facts about the
 * result. The result itself goes to state and is never repeated in the
 * thread, where every later model call would read it again.
 */
export const ToolSummarySchemas = {
  research: z.union([
    createResultSchema(
      z.object({ topic: z.string().min(1), title: z.string().min(1) }),
    ),
    NewConversationRequiredSchema,
  ]),
  makeMaterial: createResultSchema(z.object({ characters: z.int().min(1) })),
  simplify: createResultSchema(
    z.object({
      scope: z.enum(["all", "selection"]),
      characters: z.int().min(1),
    }),
  ),
  generateQuiz: createResultSchema(z.object({ questionCount: z.int().min(1) })),
  evaluate: createResultSchema(
    z.object({
      correct: EvaluationSchema.shape.correct,
      total: EvaluationSchema.shape.total,
      weakestConcept: EvaluationSchema.shape.weakestConcept,
      score: ScoreSchema,
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

export type ToolSummary<T extends SubagentTool> = z.infer<
  (typeof ToolSummarySchemas)[T]
>;
/** The `data` of a successful summary. */
export type ToolSummaryData<T extends SubagentTool> = Extract<
  ToolSummary<T>,
  { ok: true }
>["data"];

export type NewConversationRequired = z.infer<
  typeof NewConversationRequiredSchema
>;
