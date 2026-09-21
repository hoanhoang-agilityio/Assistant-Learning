import type { ToolDefinition } from "@copilotkit/runtime/v2";
import type {
  LearningState,
  Notes,
  Score,
  Settings,
  Stage,
  Status,
} from "@repo/shared/schemas";

import type { Env } from "@/types/env";

/** A JSON Patch operation. The wrapper only emits top-level `add`s. */
export interface StatePatchOperation {
  op: "add";
  path: `/${keyof LearningState}`;
  value: unknown;
}

/** The next state, and the patch that turns the previous state into it. */
export interface StateUpdate {
  state: LearningState;
  patch: StatePatchOperation[];
}

/** What a run's tools can see: the user's settings and the full state. */
export interface SupervisorRunContext {
  settings: Settings;
  /**
   * The state as of now, including results of earlier tools in the same run
   * (autopilot runs research, then notes, then the quiz).
   */
  getState: () => LearningState;
  /** Aborted when the user stops the run. */
  signal: AbortSignal;
  /** Server env, for optional keys such as `TAVILY_API_KEY`. */
  env: Env;
}

/** A web search result given to the Research Agent. */
export interface SearchResult {
  title: string;
  url: string;
  content: string;
}

export interface LearningSupervisorAgentConfig {
  /** Supervisor system prompt. */
  prompt?: string;
  /** Upper bound on LLM steps in one run. */
  maxSteps?: number;
  /** Builds the subagent tools for one run. */
  tools?: (ctx: SupervisorRunContext) => ToolDefinition[];
  /** Server env used to find provider keys. Defaults to `process.env`. */
  env?: Env;
}

/**
 * The state the Supervisor LLM sees. It never holds the full notes or quiz,
 * because `BuiltInAgent` writes the whole state into the system prompt.
 */
export interface SupervisorState {
  stage: Stage;
  status: Status;
  topic: string | null;
  research: { title: string; keyInsight: string } | null;
  notes: {
    view: Notes["view"];
    hasSimplified: boolean;
    characters: number;
  } | null;
  quiz: {
    questionCount: number;
    answeredCount: number;
    submitted: boolean;
  } | null;
  score: Score | null;
  hasFeedback: boolean;
  hasReflection: boolean;
  quizOutdated: boolean;
}
