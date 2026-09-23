import { useFrontendTool } from "@copilotkit/react-core/v2";
import {
  LEARNING_AGENT_ID,
  SET_THEME_TOOL,
} from "@repo/shared/constants/agents";
import { SetThemeParamsSchema } from "@repo/shared/schemas";

import { DisplayToolCard } from "@/components/common/DisplayToolCard";
import {
  DARK_SCHEME_QUERY,
  SET_THEME_TOOL_DESCRIPTION,
} from "@/constants/settings";
import { useSettingsActions } from "@/features/settings/hooks/use-settings-store";
import { describeTheme } from "@/features/settings/utils/settings";

/**
 * Lets the Supervisor switch the theme. The handler reads the device
 * preference when it runs, so it never acts on a stale value. Called once
 * from the app shell.
 */
export const useThemeTool = () => {
  const { setTheme } = useSettingsActions();

  useFrontendTool(
    {
      name: SET_THEME_TOOL,
      agentId: LEARNING_AGENT_ID,
      description: SET_THEME_TOOL_DESCRIPTION,
      parameters: SetThemeParamsSchema,
      handler: async ({ theme }) => {
        setTheme(theme);
        return describeTheme(
          theme,
          window.matchMedia(DARK_SCHEME_QUERY).matches,
        );
      },
      render: ({ status, args }) => (
        <DisplayToolCard status={status} detail={args.theme} />
      ),
    },
    [setTheme],
  );
};
