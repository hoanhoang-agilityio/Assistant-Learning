import { useAgentContext } from "@copilotkit/react-core/v2";

import { DISPLAY_CONTEXT_DESCRIPTION } from "@/constants/layout";
import { useResolvedTheme } from "@/features/settings/hooks/use-resolved-theme";
import { useSettings } from "@/features/settings/hooks/use-settings-store";
import { useDisplay } from "@/hooks/use-display";
import { useLayout } from "@/hooks/use-layout-store";

/**
 * Tells the Supervisor the theme and layout on screen, so "switch to dark"
 * or "show the chat" is answered from what the student actually sees.
 */
export const useDisplayContext = () => {
  const { theme } = useSettings();
  const resolvedTheme = useResolvedTheme();
  const { chatMode, viewMode } = useLayout();
  const { chat, width } = useDisplay();

  useAgentContext({
    description: DISPLAY_CONTEXT_DESCRIPTION,
    value: {
      theme,
      themeOnScreen: resolvedTheme,
      chatMode,
      chatOnScreen: chat,
      viewMode,
      width,
    },
  });
};
