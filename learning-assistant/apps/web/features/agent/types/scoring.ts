import type { Evaluation } from "@repo/shared/schemas";

/** One question graded against the answer key. */
export interface QuestionResult {
  qid: string;
  correctIndex: number;
  isCorrect: boolean;
}

/** Everything about a graded quiz that code can work out. */
export interface QuizScore {
  correct: number;
  total: number;
  percent: number;
  perQuestion: QuestionResult[];
  mastery: Evaluation["mastery"];
  weakestConcept: string | null;
}
