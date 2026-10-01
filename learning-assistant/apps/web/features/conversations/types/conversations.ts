import type { ConversationSummary } from "@repo/shared/schemas";

/** The conversation on screen. A new one has nothing to restore yet. */
export interface ActiveConversation {
  id: string;
  isNew: boolean;
}

export interface ConversationActions {
  setConversations: (conversations: ConversationSummary[]) => void;
  /** Adds the conversation, or replaces the one with its id. */
  upsertConversation: (conversation: ConversationSummary) => void;
  removeConversation: (id: string) => void;
  openConversation: (active: ActiveConversation) => void;
  setSidebarOpen: (isOpen: boolean) => void;
}

export interface ConversationStore {
  /** `null` until the first load. Kept while a refresh runs. */
  conversations: ConversationSummary[] | null;
  active: ActiveConversation | null;
  isSidebarOpen: boolean;
  actions: ConversationActions;
}
