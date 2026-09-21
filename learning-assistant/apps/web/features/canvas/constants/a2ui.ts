/** A2UI protocol version of every message the canvas builds. */
export const A2UI_VERSION = "v0.9";

/** JSON Pointer to the whole data model of a surface. */
export const DATA_MODEL_ROOT = "/";

/**
 * `forwardedProps` key for a surface action, as CopilotKit's own A2UI
 * renderer sends it; the agent reads a quiz Submit from here.
 */
export const A2UI_ACTION_PROP = "a2uiAction";
