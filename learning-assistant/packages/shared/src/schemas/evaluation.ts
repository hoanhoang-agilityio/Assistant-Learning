import { z } from "zod";

/**
 * Evaluator Agent output. Scoring is done in code; the LLM only writes a
 * per-question explanation and the overall feedback summary.
 */
export const EvaluationFeedbackSchema = z.object({
  explanations: z.array(
    z.object({
      qid: z.string().min(1),
      explanation: z
        .string()
        .min(1)
        .describe(
          "Why the correct option is right, addressing the student's answer",
        ),
    }),
  ),
  summary: z
    .string()
    .min(1)
    .describe(
      "Personalised feedback: strengths, weakest concept, what to review next",
    ),
});

export type EvaluationFeedback = z.infer<typeof EvaluationFeedbackSchema>;
