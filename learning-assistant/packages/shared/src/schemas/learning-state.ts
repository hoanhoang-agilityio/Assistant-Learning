import { z } from "zod";

import { OptionIndexSchema, QuizQuestionSchema } from "./quiz";
import { ResearchResultSchema } from "./research";

export const STAGES = [
  "idle",
  "research",
  "notes",
  "quiz",
  "evaluation",
  "score",
  "feedback",
] as const;

export const RUNNING_TASKS = [
  "research",
  "notes",
  "simplify",
  "quiz",
  "evaluate",
] as const;

export const TIERS = ["Novice", "Practitioner", "Master"] as const;

export const StageSchema = z.enum(STAGES);
export const RunningTaskSchema = z.enum(RUNNING_TASKS);
export const TierSchema = z.enum(TIERS);

const PercentSchema = z.number().min(0).max(100);

export const StatusSchema = z.object({
  running: RunningTaskSchema.nullable(),
  error: z.string().optional(),
});

export const NotesSchema = z.object({
  original: z.string(),
  simplified: z.string().nullable(),
  view: z.enum(["original", "simplified"]),
});

export const QuizSchema = z.object({
  id: z.string().min(1),
  questions: z.array(QuizQuestionSchema),
  /** Question id → chosen option index. */
  answers: z.record(z.string(), OptionIndexSchema),
  answerKeySealed: z.string().min(1),
  submitted: z.boolean(),
});

export const EvaluationSchema = z.object({
  correct: z.int().min(0),
  total: z.int().min(0),
  percent: PercentSchema,
  weakestConcept: z.string().nullable(),
  perQuestion: z.array(
    z.object({
      qid: z.string().min(1),
      correctIndex: OptionIndexSchema,
      isCorrect: z.boolean(),
      explanation: z.string(),
    }),
  ),
  mastery: z.array(z.object({ concept: z.string(), percent: PercentSchema })),
});

export const ScoreSchema = z.object({
  percent: PercentSchema,
  tier: TierSchema,
});

export const FeedbackSchema = z.object({
  /** A2UI operations from the Evaluator's `render_a2ui` call. */
  a2uiOperations: z.array(z.unknown()),
  /** Plain-text fallback shown if the surface fails to render. */
  summary: z.string(),
});

export const ReflectionSchema = z.object({
  rating: z.int().min(1).max(5),
  text: z.string(),
});

/** Shared AG-UI agent state: the single source of truth for the canvas. */
export const LearningStateSchema = z.object({
  stage: StageSchema,
  status: StatusSchema,
  topic: z.string().nullable(),
  research: ResearchResultSchema.nullable(),
  notes: NotesSchema.nullable(),
  quiz: QuizSchema.nullable(),
  evaluation: EvaluationSchema.nullable(),
  score: ScoreSchema.nullable(),
  feedback: FeedbackSchema.nullable(),
  reflection: ReflectionSchema.nullable(),
});

export type Stage = z.infer<typeof StageSchema>;
export type RunningTask = z.infer<typeof RunningTaskSchema>;
export type Tier = z.infer<typeof TierSchema>;
export type Status = z.infer<typeof StatusSchema>;
export type Notes = z.infer<typeof NotesSchema>;
export type Quiz = z.infer<typeof QuizSchema>;
export type Evaluation = z.infer<typeof EvaluationSchema>;
export type Score = z.infer<typeof ScoreSchema>;
export type Feedback = z.infer<typeof FeedbackSchema>;
export type Reflection = z.infer<typeof ReflectionSchema>;
export type LearningState = z.infer<typeof LearningStateSchema>;

export const initialLearningState: LearningState = {
  stage: "idle",
  status: { running: null },
  topic: null,
  research: null,
  notes: null,
  quiz: null,
  evaluation: null,
  score: null,
  feedback: null,
  reflection: null,
};
