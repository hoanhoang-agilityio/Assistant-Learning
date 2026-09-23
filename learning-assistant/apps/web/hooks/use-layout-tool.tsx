import { useFrontendTool } from "@copilotkit/react-core/v2";
import {
  LEARNING_AGENT_ID,
  SET_LAYOUT_TOOL,
} from "@repo/shared/constants/agents";
import { SetLayoutParamsSchema } from "@repo/shared/schemas";

import { DisplayToolCard } from "@/components/common/DisplayToolCard";
import { SET_LAYOUT_TOOL_DESCRIPTION } from "@/constants/layout";
import { useLayoutActions, useLayoutStore } from "@/hooks/use-layout-store";
import { describeDisplay, resolveDisplay } from "@/utils/layout";

/**
 * Lets the Supervisor hide, dock or pop out the chat and switch the view.
 * The result is read from the store after the change, so it describes what
 * is really on screen. Called once from the app shell.
 */
export const useLayoutTool = () => {
  const { setChatMode, setViewMode } = useLayoutActions();

  useFrontendTool(
    {
      name: SET_LAYOUT_TOOL,
      agentId: LEARNING_AGENT_ID,
      description: SET_LAYOUT_TOOL_DESCRIPTION,
      parameters: SetLayoutParamsSchema,
      handler: async ({ chat, view }) => {
        if (view) {
          setViewMode(view);
        }
        if (chat) {
          setChatMode(chat);
        }

        const { layout } = useLayoutStore.getState();
        return describeDisplay(
          layout,
          resolveDisplay(layout, window.innerWidth),
        );
      },
      render: ({ status, args }) => (
        <DisplayToolCard
          status={status}
          detail={[args.chat, args.view].filter(Boolean).join(" · ")}
        />
      ),
    },
    [setChatMode, setViewMode],
  );
};
