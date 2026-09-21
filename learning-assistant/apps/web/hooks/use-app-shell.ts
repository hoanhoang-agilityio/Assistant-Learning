import type { Provider } from "@repo/shared/schemas";
import { useLayoutEffect, useMemo, useState } from "react";

import {
  useSettings,
  useSettingsActions,
  useSettingsStore,
} from "@/features/settings/hooks/use-settings-store";
import { useThemeClass } from "@/features/settings/hooks/use-theme-class";
import { useLayoutStore } from "@/hooks/use-layout-store";

/**
 * Loads saved settings and layout, keeps the theme class in sync, and builds
 * the provider `properties` that carry the settings to the agent.
 */
export const useAppShell = (availableProviders: readonly Provider[]) => {
  const settings = useSettings();
  const { reconcileProviders } = useSettingsActions();
  const [isHydrated, setIsHydrated] = useState(false);

  // Load saved settings and layout before first paint, then drop a provider
  // whose key is gone from the server.
  useLayoutEffect(() => {
    void Promise.all([
      useSettingsStore.persist.rehydrate(),
      useLayoutStore.persist.rehydrate(),
    ]).then(() => {
      reconcileProviders(availableProviders);
      setIsHydrated(true);
    });
  }, [availableProviders, reconcileProviders]);

  useThemeClass(settings.theme, isHydrated);

  // Provider `properties` are merged into `forwardedProps` on each run.
  const properties = useMemo(() => ({ settings }), [settings]);

  return { properties };
};
