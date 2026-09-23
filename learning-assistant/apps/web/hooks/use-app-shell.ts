import { useRouter } from "next/navigation";
import { useLayoutEffect, useMemo, useState } from "react";

import { API_KEY_ROUTE } from "@/constants/routes";
import { API_KEY_HEADER } from "@/features/api-key/constants/api-key";
import {
  useApiKeyStore,
  useSealedApiKey,
} from "@/features/api-key/hooks/use-api-key-store";
import { useResolvedTheme } from "@/features/settings/hooks/use-resolved-theme";
import {
  useSettings,
  useSettingsStore,
} from "@/features/settings/hooks/use-settings-store";
import { useThemeClass } from "@/features/settings/hooks/use-theme-class";
import { useLayoutStore } from "@/hooks/use-layout-store";

/**
 * Loads the saved API key, settings and layout, sends the user to the key page
 * when no key is saved, keeps the theme class in sync, and builds what the
 * provider sends on every request: the sealed key as a header and the settings
 * as `properties`.
 */
export const useAppShell = () => {
  const router = useRouter();
  const settings = useSettings();
  const sealedKey = useSealedApiKey();
  const [isHydrated, setIsHydrated] = useState(false);

  // Load saved state before first paint.
  useLayoutEffect(() => {
    void Promise.all([
      useApiKeyStore.persist.rehydrate(),
      useSettingsStore.persist.rehydrate(),
      useLayoutStore.persist.rehydrate(),
    ]).then(() => {
      setIsHydrated(true);
    });
  }, []);

  // Also covers the key being forgotten while the assistant is open.
  useLayoutEffect(() => {
    if (isHydrated && !sealedKey) {
      router.replace(API_KEY_ROUTE);
    }
  }, [isHydrated, sealedKey, router]);

  useThemeClass(useResolvedTheme(), isHydrated);

  const headers = useMemo(
    (): Record<string, string> =>
      sealedKey ? { [API_KEY_HEADER]: sealedKey } : {},
    [sealedKey],
  );

  // Provider `properties` are merged into `forwardedProps` on each run.
  const properties = useMemo(() => ({ settings }), [settings]);

  return { isReady: isHydrated && sealedKey !== null, headers, properties };
};
