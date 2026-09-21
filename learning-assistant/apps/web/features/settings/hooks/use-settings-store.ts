import type { Settings } from "@repo/shared/schemas";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { DEFAULT_SETTINGS, SETTINGS_STORAGE_KEY } from "@/constants/settings";
import type { SettingsStore } from "@/features/settings/types/settings";
import {
  clampQuestionCount,
  parseSettings,
  reconcileProvider,
  selectModel,
  selectProvider,
} from "@/features/settings/utils/settings";
import { supportsReasoning } from "@/utils/models";
import { safeLocalStorage } from "@/utils/safe-storage";

/**
 * User settings, saved to `localStorage` and sent to the agent in
 * `forwardedProps.settings` on every run. Hydration is manual
 * (`skipHydration`) so the server render and the first client render agree;
 * `AppShell` rehydrates before paint.
 */
export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => {
      const update = (next: (settings: Settings) => Settings) =>
        set(({ settings }) => ({ settings: next(settings) }));

      return {
        settings: DEFAULT_SETTINGS,
        actions: {
          setProvider: (provider) =>
            update((settings) => selectProvider(settings, provider)),
          setModel: (model) =>
            update((settings) => selectModel(settings, model)),
          setReasoningEffort: (reasoningEffort) =>
            update((settings) =>
              supportsReasoning(settings.provider, settings.model)
                ? { ...settings, reasoningEffort }
                : settings,
            ),
          setQuestionCount: (count) =>
            update((settings) => ({
              ...settings,
              questionCount: clampQuestionCount(count),
            })),
          setLearningLevel: (learningLevel) =>
            update((settings) => ({ ...settings, learningLevel })),
          setTheme: (theme) => update((settings) => ({ ...settings, theme })),
          toggleTheme: () =>
            update((settings) => ({
              ...settings,
              theme: settings.theme === "dark" ? "light" : "dark",
            })),
          reconcileProviders: (available) =>
            update((settings) => reconcileProvider(settings, available)),
        },
      };
    },
    {
      name: SETTINGS_STORAGE_KEY,
      storage: createJSONStorage(() => safeLocalStorage),
      skipHydration: true,
      partialize: ({ settings }) => ({ settings }),
      merge: (persisted, current) => ({
        ...current,
        settings: parseSettings(
          persisted && typeof persisted === "object" && "settings" in persisted
            ? persisted.settings
            : undefined,
        ),
      }),
    },
  ),
);

export const useSettings = () => useSettingsStore((store) => store.settings);

export const useSettingsActions = () =>
  useSettingsStore((store) => store.actions);
