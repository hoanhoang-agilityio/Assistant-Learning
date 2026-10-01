import type { Settings } from "@repo/shared/schemas";
import { useEffect } from "react";

import { SETTINGS_SAVE_DELAY_MS } from "@/features/settings/constants/settings";
import {
  useSettingsActions,
  useSettingsStore,
} from "@/features/settings/hooks/use-settings-store";
import {
  fetchSavedSettings,
  saveSettings,
} from "@/features/settings/services/settings-client";

/**
 * Keeps the settings in the user's account (plan C7). Once the browser's
 * copy is loaded, the account's settings replace it; an account without any
 * gets this browser's. After that, each change is saved, a moment after
 * the last one. Without the server, the browser's copy still works.
 */
export const useSettingsSync = (isHydrated: boolean) => {
  const { replaceSettings } = useSettingsActions();

  useEffect(() => {
    if (!isHydrated) {
      return;
    }

    let isCancelled = false;
    let isLoaded = false;
    let lastSaved: string | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const scheduleSave = (settings: Settings) => {
      const json = JSON.stringify(settings);
      if (json === lastSaved) {
        return;
      }
      clearTimeout(timer);
      timer = setTimeout(() => {
        lastSaved = json;
        saveSettings(settings).catch((error: unknown) => {
          console.error("[settings] Saving failed", error);
        });
      }, SETTINGS_SAVE_DELAY_MS);
    };

    fetchSavedSettings().then(
      (saved) => {
        if (isCancelled) {
          return;
        }
        if (saved) {
          lastSaved = JSON.stringify(saved);
          replaceSettings(saved);
        } else {
          scheduleSave(useSettingsStore.getState().settings);
        }
        isLoaded = true;
      },
      (error: unknown) => {
        console.error("[settings] Loading failed", error);
      },
    );
    const unsubscribe = useSettingsStore.subscribe(({ settings }) => {
      if (isLoaded) {
        scheduleSave(settings);
      }
    });

    return () => {
      isCancelled = true;
      clearTimeout(timer);
      unsubscribe();
    };
  }, [isHydrated, replaceSettings]);
};
