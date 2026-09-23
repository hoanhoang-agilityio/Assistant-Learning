import { useLayoutEffect } from "react";

import { DARK_THEME_CLASS } from "@/constants/settings";
import type { ResolvedTheme } from "@/features/settings/types/settings";

/**
 * Keeps the `dark` class on <html> in sync with the theme on screen. The
 * inline script in the root layout sets it before first paint; this keeps it
 * right after toggles, OS switches and React's dev remount.
 */
export const useThemeClass = (theme: ResolvedTheme, isEnabled: boolean) => {
  useLayoutEffect(() => {
    if (!isEnabled) {
      return;
    }
    document.documentElement.classList.toggle(
      DARK_THEME_CLASS,
      theme === "dark",
    );
  }, [theme, isEnabled]);
};
