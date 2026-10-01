import type {
  Evaluation,
  Feedback,
  Material,
  Quiz,
  ResearchResult,
  Score,
  Stage,
} from "@repo/shared/schemas";

export interface RunRecord {
  /** The stage in the state the run saved. */
  stage: Stage;
  /** The student's newest message in the run; `null` for a Submit press. */
  userText: string | null;
}

export interface ResearchRecord {
  topic: string;
  research: ResearchResult;
}

export interface EvaluationRecord {
  /** The graded quiz, with the answers that were graded. */
  quiz: Quiz;
  evaluation: Evaluation;
  score: Score;
  feedback: Feedback;
}

/**
 * Where a conversation's history is kept outside its checkpoints: written
 * by the server when a run ends, and by each subagent tool from its own
 * result when its stage completes. Never from the browser's state.
 */
export interface LearningRecords {
  recordRun: (threadId: string, run: RunRecord) => Promise<void>;
  recordResearch: (threadId: string, record: ResearchRecord) => Promise<void>;
  recordMaterial: (threadId: string, material: Material) => Promise<void>;
  recordQuiz: (threadId: string, quiz: Quiz) => Promise<void>;
  recordEvaluation: (
    threadId: string,
    record: EvaluationRecord,
  ) => Promise<void>;
}
