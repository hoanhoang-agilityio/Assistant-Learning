import type {
  QuestionDraft,
  QuizDraft,
  ResearchDraft,
  ResearchResult,
  Source,
} from "@repo/shared/schemas";
import type { DeepPartial } from "ai";

const isPresent = <T>(value: T | undefined): value is T => value !== undefined;

/** The research written so far, with the sources found before writing. */
export const toResearchDraft = (
  partial: DeepPartial<Omit<ResearchResult, "sources">>,
  sources: Source[],
): ResearchDraft => ({
  title: partial.title ?? "",
  summary: partial.summary ?? "",
  keyInsight: partial.keyInsight ?? "",
  keyTerms: (partial.keyTerms ?? [])
    .filter(isPresent)
    .map(({ term, definition }) => ({
      term: term ?? "",
      definition: definition ?? "",
    }))
    .filter(({ term }) => term !== ""),
  sources,
});

/**
 * The questions written so far. Only the concept, question and options are
 * picked, so the answer and explanation never leave the server.
 */
export const toQuestionDrafts = (
  partial: DeepPartial<QuizDraft>,
): QuestionDraft[] =>
  (partial.questions ?? [])
    .filter(isPresent)
    .map(({ concept, question, options }) => ({
      concept: concept ?? "",
      question: question ?? "",
      options: (options ?? []).filter(
        (option): option is string => typeof option === "string",
      ),
    }))
    .filter(({ question }) => question !== "");
