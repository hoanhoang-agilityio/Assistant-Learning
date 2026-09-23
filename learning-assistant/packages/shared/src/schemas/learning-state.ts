import { z } from "zod";

import { OptionIndexSchema, QuizQuestionSchema } from "./quiz";
import { ResearchResultSchema } from "./research";

export const STAGES = [
  "idle",
  "research",
  "material",
  "quiz",
  "evaluation",
  "score",
  "feedback",
] as const;

export const RUNNING_TASKS = [
  "research",
  "material",
  "simplify",
  "quiz",
  "evaluate",
] as const;

export const TIERS = ["Novice", "Practitioner", "Master"] as const;

/** State built from the quiz. It goes out of date when the learning material changes. */
export const QUIZ_STATE_KEYS = [
  "quiz",
  "evaluation",
  "score",
  "feedback",
  "reflection",
] as const;

export const StageSchema = z.enum(STAGES);
export const RunningTaskSchema = z.enum(RUNNING_TASKS);
export const TierSchema = z.enum(TIERS);

const PercentSchema = z.number().min(0).max(100);

export const StatusSchema = z.object({
  running: RunningTaskSchema.nullable(),
  error: z.string().optional(),
  /** The task that set `error`, so the canvas can offer to retry it. */
  failed: RunningTaskSchema.optional(),
});

export const MaterialSchema = z.object({
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
  material: MaterialSchema.nullable(),
  quiz: QuizSchema.nullable(),
  evaluation: EvaluationSchema.nullable(),
  score: ScoreSchema.nullable(),
  feedback: FeedbackSchema.nullable(),
  reflection: ReflectionSchema.nullable(),
  /**
   * The student edited the learning material after a quiz existed, so the quiz and its
   * results were cleared. Reset when a new quiz, learning material or research arrive.
   */
  quizOutdated: z.boolean(),
});

export type Stage = z.infer<typeof StageSchema>;
export type RunningTask = z.infer<typeof RunningTaskSchema>;
export type Tier = z.infer<typeof TierSchema>;
export type Status = z.infer<typeof StatusSchema>;
export type Material = z.infer<typeof MaterialSchema>;
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
  material: null,
  quiz: null,
  evaluation: null,
  score: null,
  feedback: null,
  reflection: null,
  quizOutdated: false,
};
