import type { Layout } from "@/types/layout";

/** Chat panel width in px. The canvas takes the rest. */
export const CHAT_WIDTH = { min: 300, max: 760, default: 400 } as const;

/** The canvas never gets narrower than this while the chat is resized. */
export const CANVAS_MIN_WIDTH = 480;

/** Keyboard step (arrow keys) for the resize handle, in px. */
export const CHAT_RESIZE_STEP = 24;

/** `localStorage` key for the persisted layout store. */
export const LAYOUT_STORAGE_KEY = "learning-assistant:layout";

/** Set on <body> while the divider is dragged: no text selection, resize cursor. */
export const RESIZING_BODY_CLASS = "is-resizing-panels";

export const DEFAULT_LAYOUT: Layout = {
  chatWidth: CHAT_WIDTH.default,
  chatMode: "docked",
  viewMode: "auto",
};

/**
 * Below this width the docked chat and the canvas no longer fit side by side,
 * so a docked chat is shown as a popup instead.
 */
export const COMPACT_MAX_WIDTH = CHAT_WIDTH.min + CANVAS_MIN_WIDTH;

/** Frame width in px for the previewed device layouts. */
export const DEVICE_WIDTHS = { tablet: 768, mobile: 390 } as const;

/** Window width assumed before the browser reports one. */
export const FALLBACK_WINDOW_WIDTH = 1280;

/** The popup chat's width in px, and its gap to the page edge. */
export const POPUP_SIZE = { width: 420, gutter: 24 } as const;

export const SET_LAYOUT_TOOL_DESCRIPTION =
  "Change how the page is laid out: show the chat docked beside the canvas, " +
  "as a popup over it, or hide it; and switch the view to auto (follows the " +
  "window), desktop, tablet or mobile. Send only what the student asked to " +
  "change. The result says what is now on screen.";

/** Chat card copy for the theme and layout tools. */
export const DISPLAY_TOOL_COPY = {
  running: "Updating the display",
  done: "Display updated",
} as const;

export const DISPLAY_CONTEXT_DESCRIPTION =
  "Current theme and page layout: chosen theme and the one on screen, chosen " +
  "chat mode and the one on screen, view mode, and page width in px";

/** Keys that resize the chat from the keyboard. */
export const RESIZE_KEYS = {
  narrower: "ArrowLeft",
  wider: "ArrowRight",
  reset: "Enter",
} as const;

/** DOM id of the chat panel, for the collapse buttons' `aria-controls`. */
export const CHAT_PANEL_ID = "assistant-chat-panel";
