import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { API_KEY_STORAGE_KEY } from "@/features/api-key/constants/api-key";
import type { ApiKeyStore } from "@/features/api-key/types/api-key";
import { safeSessionStorage } from "@/utils/safe-storage";

/**
 * The sealed OpenAI API key, saved to `sessionStorage` (cleared when the tab
 * closes). Hydration is manual (`skipHydration`) so the server render and the
 * first client render agree; call `persist.rehydrate()` before reading it.
 */
export const useApiKeyStore = create<ApiKeyStore>()(
  persist(
    (set) => ({
      sealedKey: null,
      actions: {
        setSealedKey: (sealedKey) => set({ sealedKey }),
        clearSealedKey: () => set({ sealedKey: null }),
      },
    }),
    {
      name: API_KEY_STORAGE_KEY,
      storage: createJSONStorage(() => safeSessionStorage),
      skipHydration: true,
      partialize: ({ sealedKey }) => ({ sealedKey }),
      merge: (persisted, current) => ({
        ...current,
        sealedKey:
          persisted &&
          typeof persisted === "object" &&
          "sealedKey" in persisted &&
          typeof persisted.sealedKey === "string"
            ? persisted.sealedKey
            : null,
      }),
    },
  ),
);

export const useSealedApiKey = () => useApiKeyStore((store) => store.sealedKey);

export const useApiKeyActions = () => useApiKeyStore((store) => store.actions);
