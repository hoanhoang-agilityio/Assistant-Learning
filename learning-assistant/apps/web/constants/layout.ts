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
  isChatOpen: true,
};

/** Keys that resize the chat from the keyboard. */
export const RESIZE_KEYS = {
  narrower: "ArrowLeft",
  wider: "ArrowRight",
  reset: "Enter",
} as const;

/** DOM id of the chat panel, for the collapse buttons' `aria-controls`. */
export const CHAT_PANEL_ID = "assistant-chat-panel";
