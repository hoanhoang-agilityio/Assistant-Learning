import { usePrefersDark } from "@/features/settings/hooks/use-prefers-dark";
import { useSettings } from "@/features/settings/hooks/use-settings-store";
import { resolveTheme } from "@/features/settings/utils/settings";

/** The theme on screen: the saved one, with `system` following the device. */
export const useResolvedTheme = () => {
  const { theme } = useSettings();
  const prefersDark = usePrefersDark();

  return resolveTheme(theme, prefersDark);
};
