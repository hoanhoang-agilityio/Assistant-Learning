import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { CONVERSATIONS_STORAGE_KEY } from "@/features/conversations/constants/conversations";
import type { ConversationStore } from "@/features/conversations/types/conversations";
import { safeLocalStorage } from "@/utils/safe-storage";

/**
 * The user's conversations and which one is open. Only the open one's id
 * and the sidebar's open state are saved, so a reload reopens the same
 * conversation; the list always comes from the server. Hydrates manually
 * from `AppShell`, like the other stores.
 */
export const useConversationStore = create<ConversationStore>()(
  persist(
    (set) => ({
      conversations: null,
      active: null,
      isSidebarOpen: true,
      actions: {
        setConversations: (conversations) => set({ conversations }),
        upsertConversation: (conversation) =>
          set(({ conversations }) => {
            const list = conversations ?? [];
            return {
              conversations: list.some(({ id }) => id === conversation.id)
                ? list.map((existing) =>
                    existing.id === conversation.id ? conversation : existing,
                  )
                : [conversation, ...list],
            };
          }),
        updateConversation: (conversation) =>
          set(({ conversations }) => ({
            conversations:
              conversations?.map((existing) =>
                existing.id === conversation.id ? conversation : existing,
              ) ?? null,
          })),
        removeConversation: (id) =>
          set(({ conversations }) => ({
            conversations: (conversations ?? []).filter(
              (conversation) => conversation.id !== id,
            ),
          })),
        openConversation: (active) => set({ active }),
        setSidebarOpen: (isSidebarOpen) => set({ isSidebarOpen }),
      },
    }),
    {
      name: CONVERSATIONS_STORAGE_KEY,
      storage: createJSONStorage(() => safeLocalStorage),
      skipHydration: true,
      partialize: ({ active, isSidebarOpen }) => ({
        activeId: active?.id,
        isSidebarOpen,
      }),
      merge: (persisted, current) => {
        const saved = (persisted ?? {}) as {
          activeId?: unknown;
          isSidebarOpen?: unknown;
        };
        return {
          ...current,
          // Only the id is kept; whether it still exists is checked on load.
          active:
            typeof saved.activeId === "string"
              ? { id: saved.activeId, isNew: false }
              : null,
          isSidebarOpen:
            typeof saved.isSidebarOpen === "boolean"
              ? saved.isSidebarOpen
              : current.isSidebarOpen,
        };
      },
    },
  ),
);

export const useConversations = () =>
  useConversationStore((store) => store.conversations);

export const useActiveConversation = () =>
  useConversationStore((store) => store.active);

export const useIsSidebarOpen = () =>
  useConversationStore((store) => store.isSidebarOpen);

export const useConversationActions = () =>
  useConversationStore((store) => store.actions);
