import {
  type EvaluationFeedback,
  EvaluationFeedbackSchema,
} from "@repo/shared/schemas";

import {
  createEvaluatorPrompt,
  createEvaluatorSystem,
} from "@/features/agent/services/prompts/evaluator";
import { generateStructured } from "@/features/agent/services/subagents/generate-structured";
import type { EvaluatorInput } from "@/features/agent/types/scoring";
import type { RunSettings } from "@/types/llm";

interface EvaluatorParams {
  input: EvaluatorInput;
  settings: RunSettings;
  signal?: AbortSignal;
}

/**
 * Evaluator Agent, text part: an explanation for each graded question and a
 * personal feedback summary, written from the grading and the learning material.
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
