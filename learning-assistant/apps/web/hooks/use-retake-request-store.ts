import { create } from "zustand";

import type { RetakeRequestStore } from "@/types/retake-request";

/**
 * Carries a Retake from the History page's link to the canvas: the app
 * shell sets it, the conversation bootstrap opens that conversation, and
 * the canvas retakes its quiz once the state is back. Not persisted: a
 * reload must not retake again.
 */
export const useRetakeRequestStore = create<RetakeRequestStore>()((set) => ({
  conversationId: null,
  actions: {
    requestRetake: (conversationId) => set({ conversationId }),
    clearRetake: () => set({ conversationId: null }),
  },
}));

export const useRetakeConversationId = () =>
  useRetakeRequestStore((store) => store.conversationId);

export const useRetakeRequestActions = () =>
  useRetakeRequestStore((store) => store.actions);
