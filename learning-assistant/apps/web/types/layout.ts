export interface Layout {
  /** Chat panel width in px. */
  chatWidth: number;
  isChatOpen: boolean;
}

export interface LayoutActions {
  /** Sets the chat width, clamped to its limits and the space available. */
  setChatWidth: (width: number, containerWidth?: number) => void;
  resetChatWidth: () => void;
  toggleChat: () => void;
}

export interface LayoutStore {
  layout: Layout;
  actions: LayoutActions;
}
