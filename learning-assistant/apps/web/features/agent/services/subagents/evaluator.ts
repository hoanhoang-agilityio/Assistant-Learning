import {
  type EvaluationFeedback,
  EvaluationFeedbackSchema,
  type Settings,
} from "@repo/shared/schemas";

import {
  createEvaluatorPrompt,
  createEvaluatorSystem,
} from "@/features/agent/services/prompts/evaluator";
import { generateStructured } from "@/features/agent/services/subagents/generate-structured";
import type { EvaluatorInput } from "@/features/agent/types/scoring";

interface EvaluatorParams {
  input: EvaluatorInput;
  settings: Settings;
  signal?: AbortSignal;
}

/**
 * Evaluator Agent, text part: an explanation for each graded question and a
 * personal feedback summary, written from the grading and the notes.
 */
export const runEvaluator = ({
  input,
  settings,
  signal,
}: EvaluatorParams): Promise<EvaluationFeedback> =>
  generateStructured({
    settings,
    system: createEvaluatorSystem(settings.learningLevel),
    prompt: createEvaluatorPrompt(input),
    schema: EvaluationFeedbackSchema,
    signal,
  });
