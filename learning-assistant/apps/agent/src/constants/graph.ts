import { initialLearningState, type LearningState } from "@repo/shared/schemas";

/**
 * State keys the adapter keeps in a run's input. The browser sends its whole
 * state, which would overwrite the checkpoint key by key; everything but
 * these is cut before the in-process client sees it. The client then takes
 * only a few fields from them (see `applyClientEdits`), never a key as it is.
 */
export const CLIENT_INPUT_STATE_KEYS = [
  "quiz",
  "material",
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

/**
 * The tool call the A2UI middleware adds to the messages for a surface
 * action such as the quiz Submit (`@ag-ui/a2ui-middleware`'s own name).
 */
export const A2UI_ACTION_TOOL = "log_a2ui_event";

/** The custom graph event the AG-UI adapter turns into a state snapshot. */
export const MANUAL_STATE_EVENT = "manually_emit_state";

/**
 * Graph steps allowed in one run. Every model call and tool call is a step,
 * and so is each middleware hook around them, so LangGraph's default of 25
 * ends a three-tool run early. What really bounds a run is the cap on model
 * calls (`SUPERVISOR_MAX_STEPS`); this only has to stay above it.
 */
export const GRAPH_RECURSION_LIMIT = 150;

/** Headings of what the Supervisor's prompt calls by name. */
export const APP_CONTEXT_HEADING = "## Context from the application";
export const APP_STATE_HEADING = "## Application State";
