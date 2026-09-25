/** A2UI protocol version of every message the canvas builds. */
export const A2UI_VERSION = "v0.9";

/** Top-level keys of the A2UI operations a stored surface may hold. */
export const SURFACE_OPERATION_KEYS = [
  "createSurface",
  "updateComponents",
  "updateDataModel",
] as const;

/** JSON Pointer to the whole data model of a surface. */
export const DATA_MODEL_ROOT = "/";

/**
 * `forwardedProps` key for a surface action, as CopilotKit's own A2UI
 * renderer sends it; the agent reads a quiz Submit from here.
 */
export const A2UI_ACTION_PROP = "a2uiAction";

/** A fixed surface whose messages were rejected; the reason follows. */
export const SURFACE_ERROR_PREFIX = "This stage could not be drawn";

/** A fixed surface whose component threw while rendering. */
export const SURFACE_RENDER_ERROR =
  "This stage could not be drawn. Try moving to another stage and back, or reload the page.";

/** A Board view whose operations were rejected or whose component threw. */
export const BOARD_SURFACE_ERROR =
  "This view could not be drawn. Ask the assistant to make it again.";
