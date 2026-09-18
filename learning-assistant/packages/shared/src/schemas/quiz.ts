import { z } from "zod";

export const OPTIONS_PER_QUESTION = 4;

export const OptionIndexSchema = z
  .int()
  .min(0)
  .max(OPTIONS_PER_QUESTION - 1);

const OptionsSchema = z.array(z.string().min(1)).length(OPTIONS_PER_QUESTION);

/**
 * Quiz Agent output. It still holds the answers: the `generateQuiz` tool
 * assigns ids, seals `correctIndex` + `explanation` into the answer key, and
 * writes only the public part to state (`QuizQuestionSchema`).
 */
export const QuizDraftQuestionSchema = z.object({
  concept: z
    .string()
    .min(1)
    .describe("Short name of the concept this question tests"),
  question: z.string().min(1),
  options: OptionsSchema,
  correctIndex: OptionIndexSchema,
  explanation: z.string().min(1).describe("Why the correct option is right"),
});

export const QuizDraftSchema = z.object({
  questions: z.array(QuizDraftQuestionSchema).min(1),
});

/** A question as the client sees it: no answer, no explanation. */
export const QuizQuestionSchema = z.object({
  id: z.string().min(1),
  concept: z.string().min(1),
  question: z.string().min(1),
  options: OptionsSchema,
});

/** The plaintext that gets sealed into `quiz.answerKeySealed`. */
export const AnswerKeySchema = z.object({
  correctIndex: z.array(OptionIndexSchema),
  explanations: z.array(z.string()),
});

export type QuizDraftQuestion = z.infer<typeof QuizDraftQuestionSchema>;
export type QuizDraft = z.infer<typeof QuizDraftSchema>;
export type QuizQuestion = z.infer<typeof QuizQuestionSchema>;
export type AnswerKey = z.infer<typeof AnswerKeySchema>;
