import type { SubagentTool } from "@repo/shared/schemas";

/** Progress-card copy for each subagent tool. */
export const TOOL_LABELS: Record<
  SubagentTool,
  { running: string; done: string; failed: string; stopped: string }
> = {
  research: {
    running: "Researching",
    done: "Research ready",
    failed: "Research failed",
    stopped: "Research stopped",
  },
  makeNotes: {
    running: "Writing notes",
    done: "Notes ready",
    failed: "Notes failed",
    stopped: "Notes stopped",
  },
  simplify: {
    running: "Simplifying notes",
    done: "Notes simplified",
    failed: "Simplify failed",
    stopped: "Simplify stopped",
  },
  generateQuiz: {
    running: "Writing quiz questions",
    done: "Quiz ready",
    failed: "Quiz failed",
    stopped: "Quiz stopped",
  },
  evaluate: {
    running: "Evaluating your answers",
    done: "Evaluation ready",
    failed: "Evaluation failed",
    stopped: "Evaluation stopped",
  },
};

/** The card under a finished evaluation that opens the Feedback stage. */
export const FEEDBACK_READY_COPY = {
  title: "Feedback ready",
  hint: "see your personal feedback",
} as const;
