import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { DEFAULT_LAYOUT, LAYOUT_STORAGE_KEY } from "@/constants/layout";
import type { LayoutStore } from "@/types/layout";
import { clampChatWidth, parseLayout } from "@/utils/layout";
import { safeLocalStorage } from "@/utils/safe-storage";

/**
 * Chat width and open/closed state, saved to `localStorage`. Like the
 * settings store it hydrates manually, from `AppShell`, so the server render
 * and the first client render agree.
 */
export const useLayoutStore = create<LayoutStore>()(
  persist(
    (set) => ({
      layout: DEFAULT_LAYOUT,
      actions: {
        setChatWidth: (width, containerWidth) =>
          set(({ layout }) => ({
            layout: {
              ...layout,
              chatWidth: clampChatWidth(width, containerWidth),
            },
          })),
        resetChatWidth: () =>
          set(({ layout }) => ({
            layout: { ...layout, chatWidth: DEFAULT_LAYOUT.chatWidth },
          })),
        toggleChat: () =>
          set(({ layout }) => ({
            layout: { ...layout, isChatOpen: !layout.isChatOpen },
          })),
      },
    }),
    {
      name: LAYOUT_STORAGE_KEY,
      storage: createJSONStorage(() => safeLocalStorage),
      skipHydration: true,
      partialize: ({ layout }) => ({ layout }),
      merge: (persisted, current) => ({
        ...current,
        layout: parseLayout(
          persisted && typeof persisted === "object" && "layout" in persisted
            ? persisted.layout
            : undefined,
        ),
      }),
    },
  ),
);

export const useLayout = () => useLayoutStore((store) => store.layout);

export const useLayoutActions = () => useLayoutStore((store) => store.actions);
