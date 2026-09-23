import { type QuizDraft, QuizDraftQuestionSchema } from "@repo/shared/schemas";
import { z } from "zod";

import { QUIZ_ATTEMPTS } from "@/features/agent/constants/agents";
import {
  createQuizPrompt,
  createQuizSystem,
} from "@/features/agent/services/prompts/subagents";
import { generateStructured } from "@/features/agent/services/subagents/generate-structured";
import type { RunSettings } from "@/types/llm";

interface QuizParams {
  /** The learning material in the view the student is looking at. */
  material: string;
  count: number;
  settings: RunSettings;
  signal?: AbortSignal;
}

/** A draft with exactly `count` questions, each with a concept and 4 options. */
const createQuizDraftSchema = (count: number) =>
  z.object({ questions: z.array(QuizDraftQuestionSchema).length(count) });

/**
 * Quiz Agent: `count` multiple-choice questions from the learning material, with the
 * answers still in them (the `generateQuiz` tool seals those). A reply that
 * fails the schema, including the wrong number of questions, is retried once.
 */
export const runQuiz = async ({
  material,
  count,
  settings,
  signal,
}: QuizParams): Promise<QuizDraft> => {
  const schema = createQuizDraftSchema(count);
  let lastError: unknown;

  for (let attempt = 1; attempt <= QUIZ_ATTEMPTS; attempt += 1) {
    try {
      return await generateStructured({
        settings,
        system: createQuizSystem(settings.learningLevel),
        prompt: createQuizPrompt(material, count),
        schema,
        signal,
      });
    } catch (error) {
      if (signal?.aborted) {
        throw error;
      }
      lastError = error;
      console.warn(`[quiz] Attempt ${attempt} failed.`, error);
    }
  }
  throw lastError;
};
