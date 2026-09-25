import {
  type LearningLevel,
  type LearningState,
  QUIZ_STATE_KEYS,
  type RunningTask,
  type Stage,
  type SubagentTool,
} from "@repo/shared/schemas";

/** The student's side of a turn in the LangSmith trace when Submit started it. */
export const QUIZ_SUBMIT_TURN = "Submitted the quiz.";

/** Upper bound on LLM steps (tool calls and replies) in one Supervisor run. */
export const SUPERVISOR_MAX_STEPS = 8;

/**
 * Internal `CUSTOM` events that carry streamed output to `syncStateFromTools`,
 * which turns them into state and never forwards them.
 */
export const DRAFT_EVENTS = {
  stage: "learning.stageDraft",
  board: "learning.boardDraft",
} as const;

/**
 * Least time between two streamed drafts of the same output. Each one sends
 * the whole draft, so this bounds the traffic while text streams in.
 */
export const DRAFT_INTERVAL_MS = 120;

/** `status.running` while each subagent tool runs. */
export const SUBAGENT_TASK: Record<SubagentTool, RunningTask> = {
  research: "research",
  makeMaterial: "material",
  simplify: "simplify",
  generateQuiz: "quiz",
  evaluate: "evaluate",
};

/** The stage the canvas moves to when each subagent tool succeeds. */
export const SUBAGENT_STAGE: Record<SubagentTool, Stage> = {
  research: "research",
  makeMaterial: "material",
  simplify: "material",
  generateQuiz: "quiz",
  evaluate: "evaluation",
};

/** Later stages that go out of date when each subagent tool succeeds. */
export const SUBAGENT_CLEARS: Record<
  SubagentTool,
  readonly (keyof LearningState)[]
> = {
  research: ["material", ...QUIZ_STATE_KEYS],
  makeMaterial: QUIZ_STATE_KEYS,
  simplify: QUIZ_STATE_KEYS,
  generateQuiz: ["evaluation", "score", "feedback", "reflection"],
  evaluate: ["reflection"],
};

/** How each subagent adapts its writing to the student's level. */
export const LEVEL_GUIDANCE: Record<LearningLevel, string> = {
  beginner:
    "The student is a beginner. Use plain words and short sentences, define every technical term the first time it appears, and prefer everyday examples and analogies.",
  intermediate:
    "The student knows the basics. Use the field's usual terms with a short reminder of what they mean, and connect new ideas to what they likely know.",
  advanced:
    "The student is advanced. Use precise terminology, go into mechanisms, trade-offs and edge cases, and skip introductory explanations.",
};

/** Env variable that turns on web research. */
export const TAVILY_ENV_KEY = "TAVILY_API_KEY";

export const TAVILY_SEARCH_URL = "https://api.tavily.com/search";

/** Web results passed to the Research Agent, and cited as sources. */
export const TAVILY_MAX_RESULTS = 5;

/** Upper bound on the text of each web result given to the model. */
export const SEARCH_RESULT_MAX_CHARS = 2000;

/** Env variable holding the secret the quiz answer key is sealed with. */
export const QUIZ_SEAL_SECRET_ENV_KEY = "QUIZ_SEAL_SECRET";

/** Quiz Agent calls before giving up: the first try plus one retry. */
export const QUIZ_ATTEMPTS = 2;

/** Feedback surface attempts: the first try plus one retry with the errors. */
export const FEEDBACK_SURFACE_ATTEMPTS = 2;

/**
 * Every agent context entry CopilotKit's A2UI support adds starts with this:
 * the catalog, its schemas and generic generation and design guidelines
 * (about 3,000 tokens). The Supervisor does not need them.
 */
export const A2UI_CONTEXT_PREFIX = "A2UI ";
