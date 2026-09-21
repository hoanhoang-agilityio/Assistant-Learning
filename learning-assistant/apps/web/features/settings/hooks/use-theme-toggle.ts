import {
  useSettings,
  useSettingsActions,
} from "@/features/settings/hooks/use-settings-store";

/** The current theme and a handler that flips it. */
export const useThemeToggle = () => {
  const { theme } = useSettings();
  const { toggleTheme } = useSettingsActions();

  return { isDark: theme === "dark", handleToggleTheme: toggleTheme };
};
