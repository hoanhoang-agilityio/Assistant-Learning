import type { Theme } from "@repo/shared/schemas";
import { useLayoutEffect } from "react";

/**
 * Keeps the `dark` class on <html> in sync with the theme setting. The inline
 * script in the root layout sets it before first paint; this keeps it right
 * after toggles and after React's dev remount clears it.
 */
export const useThemeClass = (theme: Theme, isEnabled: boolean) => {
  useLayoutEffect(() => {
    if (!isEnabled) {
      return;
    }
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme, isEnabled]);
};
