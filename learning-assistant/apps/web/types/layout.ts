import type { ChatMode, ViewMode } from "@repo/shared/schemas";

export interface Layout {
  /** Chat panel width in px, while docked. */
  chatWidth: number;
  /** The chat mode the user chose; a narrow screen may show it as a popup. */
  chatMode: ChatMode;
  viewMode: ViewMode;
}

/** The layout on screen, after the window width is taken into account. */
export interface Display {
  /** Width of the device frame in px, or null when the page fills the window. */
  frameWidth: number | null;
  /** Width the page lays itself out in, in px. */
  width: number;
  /** Too narrow to dock the chat beside the canvas. */
  isCompact: boolean;
  /** How the chat is actually shown. */
  chat: ChatMode;
}

export interface LayoutActions {
  /** Sets the chat width, clamped to its limits and the space available. */
  setChatWidth: (width: number, containerWidth?: number) => void;
  resetChatWidth: () => void;
  /** Also expands the popup when the mode is `popup`. */
  setChatMode: (mode: ChatMode) => void;
  setViewMode: (mode: ViewMode) => void;
  setPopupOpen: (isOpen: boolean) => void;
}

export interface LayoutStore {
  layout: Layout;
  /** Whether the popup chat is expanded. Not saved. */
  isPopupOpen: boolean;
  actions: LayoutActions;
}
