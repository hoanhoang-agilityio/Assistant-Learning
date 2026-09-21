import type {
  LearningState,
  RunningTask,
  Stage,
  SubagentTool,
} from "@repo/shared/schemas";

/** Upper bound on LLM steps (tool calls and replies) in one Supervisor run. */
export const SUPERVISOR_MAX_STEPS = 8;

/** `status.running` while each subagent tool runs. */
export const SUBAGENT_TASK: Record<SubagentTool, RunningTask> = {
  research: "research",
  makeNotes: "notes",
  simplify: "simplify",
  generateQuiz: "quiz",
  evaluate: "evaluate",
};

/** The stage the canvas moves to when each subagent tool succeeds. */
export const SUBAGENT_STAGE: Record<SubagentTool, Stage> = {
  research: "research",
  makeNotes: "notes",
  simplify: "notes",
  generateQuiz: "quiz",
  evaluate: "evaluation",
};

/** Later stages that go out of date when each subagent tool succeeds. */
export const SUBAGENT_CLEARS: Record<SubagentTool, (keyof LearningState)[]> = {
  research: ["notes", "quiz", "evaluation", "score", "feedback", "reflection"],
  makeNotes: ["quiz", "evaluation", "score", "feedback", "reflection"],
  simplify: ["quiz", "evaluation", "score", "feedback", "reflection"],
  generateQuiz: ["evaluation", "score", "feedback", "reflection"],
  evaluate: ["reflection"],
};
