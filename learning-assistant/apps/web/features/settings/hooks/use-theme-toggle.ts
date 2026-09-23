import { useResolvedTheme } from "@/features/settings/hooks/use-resolved-theme";
import { useSettingsActions } from "@/features/settings/hooks/use-settings-store";

/**
 * Whether the screen is dark, and a handler that switches to the other
 * theme. Toggling leaves `system` for an explicit light or dark.
 */
export const useThemeToggle = () => {
  const isDark = useResolvedTheme() === "dark";
  const { setTheme } = useSettingsActions();

  return {
    isDark,
    handleToggleTheme: () => setTheme(isDark ? "light" : "dark"),
  };
};
