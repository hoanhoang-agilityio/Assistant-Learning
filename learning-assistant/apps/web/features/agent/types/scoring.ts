import type { Evaluation, Tier } from "@repo/shared/schemas";

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

/** A graded question with everything the Evaluator needs to explain it. */
export interface GradedQuestion {
  qid: string;
  concept: string;
  question: string;
  options: string[];
  chosenIndex: number | null;
  correctIndex: number;
  isCorrect: boolean;
  /** The Quiz Agent's explanation from the answer key; the fallback. */
  keyExplanation: string;
}

/** What the Evaluator Agent writes feedback from: the grading and the notes. */
export interface EvaluatorInput {
  questions: GradedQuestion[];
  score: QuizScore;
  tier: Tier;
  /** The notes the student was quizzed on. */
  notes: string;
}
