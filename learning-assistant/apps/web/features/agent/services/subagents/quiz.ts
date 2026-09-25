import {
  type QuestionDraft,
  type QuizDraft,
  QuizDraftQuestionSchema,
} from "@repo/shared/schemas";
import { z } from "zod";

import { QUIZ_ATTEMPTS } from "@/features/agent/constants/agents";
import {
  createQuizPrompt,
  createQuizSystem,
} from "@/features/agent/services/prompts/subagents";
import { generateStructured } from "@/features/agent/services/subagents/generate-structured";
import { toQuestionDrafts } from "@/features/agent/utils/drafts";
import type { RunSettings } from "@/types/llm";

interface QuizParams {
  /** The learning material in the view the student is looking at. */
  material: string;
  count: number;
  settings: RunSettings;
  signal?: AbortSignal;
  /** Called with the questions written so far, without their answers. */
  onDraft?: (questions: QuestionDraft[]) => void;
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
  onDraft,
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
        onPartial: onDraft
          ? (partial) => onDraft(toQuestionDrafts(partial))
          : undefined,
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
