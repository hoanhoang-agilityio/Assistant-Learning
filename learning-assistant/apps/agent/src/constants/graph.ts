import { initialLearningState, type LearningState } from "@repo/shared/schemas";

/**
 * State keys the browser may write. The browser sends its whole state as a
 * run's input, which would overwrite the checkpoint key by key; the input is
 * cut down to these, so it cannot replace what the server wrote. Whole
 * top-level keys only: a client field nested in a server key (the answers
 * in `quiz`, an edit of `material`) has to move up before it can be listed.
 */
export const CLIENT_WRITABLE_STATE_KEYS = [
  "reflection",
] as const satisfies readonly (keyof LearningState)[];

/**
 * State keys the browser sees in a state snapshot: the canvas's
 * `LearningState`. Anything else the graph keeps stays on the server.
 */
export const CLIENT_VISIBLE_STATE_KEYS: readonly string[] =
  Object.keys(initialLearningState);

/** Where the AG-UI adapter puts the run's frontend tools in the input. */
export const FRONTEND_TOOLS_INPUT_KEY = "copilotkit";

/** Where the AG-UI adapter puts the run's `useAgentContext` entries in the input. */
export const APP_CONTEXT_INPUT_KEY = "ag-ui";

/**
 * `LangGraphAgent` wants a deployment URL even when it is given a client.
 * Nothing is ever requested from it: the graph runs in this process.
 */
export const IN_PROCESS_DEPLOYMENT_URL = "inproc://learning";

/** Holds the process's thread checkpoints on `globalThis`. */
export const CHECKPOINTER_GLOBAL_KEY = "__learningThreadCheckpointer";

/** The run that replays a thread from its checkpoint on reload. */
export const RELOAD_RUN_ID = "reload";

/**
 * Stands in for an API key in a graph that only reads checkpoints. Its model
 * is never called.
 */
export const NO_API_KEY = "not-used";

/** Headings of what the Supervisor's prompt calls by name. */
export const APP_CONTEXT_HEADING = "## Context from the application";
export const APP_STATE_HEADING = "## Application State";
