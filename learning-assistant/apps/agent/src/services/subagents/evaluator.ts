import {
  type EvaluationFeedback,
  EvaluationFeedbackSchema,
} from "@repo/shared/schemas";
import type { DeepPartial } from "ai";

import type { RunSettings } from "../../types/llm";
import type { EvaluatorInput } from "../../types/scoring";
import {
  createEvaluatorPrompt,
  createEvaluatorSystem,
} from "../prompts/evaluator";
import { generateStructured } from "./generate-structured";

interface EvaluatorParams {
  input: EvaluatorInput;
  settings: RunSettings;
  signal?: AbortSignal;
  /** Called with the explanations and summary written so far. */
  onPartial?: (partial: DeepPartial<EvaluationFeedback>) => void;
}

/**
 * Evaluator Agent, text part: an explanation for each graded question and a
 * personal feedback summary, written from the grading and the learning material.
 */
export const runEvaluator = ({
  input,
  settings,
  signal,
  onPartial,
}: EvaluatorParams): Promise<EvaluationFeedback> =>
  generateStructured({
    settings,
    system: createEvaluatorSystem(settings.learningLevel),
    prompt: createEvaluatorPrompt(input),
    schema: EvaluationFeedbackSchema,
    signal,
    onPartial,
  });
