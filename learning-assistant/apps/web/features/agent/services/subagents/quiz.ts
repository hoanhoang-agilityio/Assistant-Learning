import {
  type QuizDraft,
  QuizDraftQuestionSchema,
  type Settings,
} from "@repo/shared/schemas";
import { z } from "zod";

import { QUIZ_ATTEMPTS } from "@/features/agent/constants/agents";
import {
  createQuizPrompt,
  createQuizSystem,
} from "@/features/agent/services/prompts/subagents";
import { generateStructured } from "@/features/agent/services/subagents/generate-structured";

interface QuizParams {
  /** The notes in the view the student is looking at. */
  notes: string;
  count: number;
  settings: Settings;
  signal?: AbortSignal;
}

/** A draft with exactly `count` questions, each with a concept and 4 options. */
const createQuizDraftSchema = (count: number) =>
  z.object({ questions: z.array(QuizDraftQuestionSchema).length(count) });

/**
 * Quiz Agent: `count` multiple-choice questions from the notes, with the
 * answers still in them (the `generateQuiz` tool seals those). A reply that
 * fails the schema, including the wrong number of questions, is retried once.
 */
export const runQuiz = async ({
  notes,
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
        prompt: createQuizPrompt(notes, count),
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
