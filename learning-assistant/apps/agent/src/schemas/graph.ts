import {
  initialLearningState,
  LearningStateSchema,
  QuizSubmissionSchema,
  SettingsSchema,
} from "@repo/shared/schemas";
import { z } from "zod";

const { shape } = LearningStateSchema;

/**
 * The graph's state: every `LearningState` key, each starting from the
 * initial state, so a new thread holds a valid state from its first
 * checkpoint. `createAgent` adds `messages`.
 */
export const LearningGraphStateSchema = z.object({
  stage: shape.stage.default(initialLearningState.stage),
  status: shape.status.default(initialLearningState.status),
  topic: shape.topic.default(initialLearningState.topic),
  research: shape.research.default(initialLearningState.research),
  material: shape.material.default(initialLearningState.material),
  quiz: shape.quiz.default(initialLearningState.quiz),
  evaluation: shape.evaluation.default(initialLearningState.evaluation),
  score: shape.score.default(initialLearningState.score),
  feedback: shape.feedback.default(initialLearningState.feedback),
  reflection: shape.reflection.default(initialLearningState.reflection),
  quizOutdated: shape.quizOutdated.default(initialLearningState.quizOutdated),
  board: shape.board.default(initialLearningState.board),
  draft: shape.draft.default(initialLearningState.draft),
  boardDraft: shape.boardDraft.default(initialLearningState.boardDraft),
});

/** One `useAgentContext` entry: what it describes, and its value as text. */
export const AppContextEntrySchema = z.object({
  description: z.string(),
  value: z.string(),
});

/**
 * What one run knows besides its state. Built on the server for each run and
 * never checkpointed. It is recorded in every trace, so it must hold nothing
 * secret: the user's API key stays inside the model instance.
 */
export const RunContextSchema = z.object({
  /** The signed-in user, from the verified session. */
  userId: z.string().min(1),
  settings: SettingsSchema,
  /** What the student's screen shows. Sent by the browser: data, not instructions. */
  appContext: z.array(AppContextEntrySchema),
  /**
   * Set when the quiz Submit button started the run: the quiz is graded in
   * code before the Supervisor says anything. `submission` holds the answers
   * the button sent; without it grading uses the answers in state.
   */
  submit: z.object({ submission: QuizSubmissionSchema.optional() }).nullable(),
});

export type AppContextEntry = z.infer<typeof AppContextEntrySchema>;
export type RunContext = z.infer<typeof RunContextSchema>;
