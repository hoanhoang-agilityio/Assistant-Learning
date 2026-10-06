import { useRef } from "react";

import { useRetakeFromHistory } from "@/features/canvas/hooks/use-retake-from-history";
import { useChatUiTools } from "@/features/chat/hooks/use-chat-ui-tools";
import { useStageSuggestions } from "@/features/chat/hooks/use-stage-suggestions";
import { useToolRenderers } from "@/features/chat/hooks/use-tool-renderers";
import { useConversationRefresh } from "@/features/conversations/hooks/use-conversation-refresh";
import { useConversationTitle } from "@/features/conversations/hooks/use-conversation-title";
import { useDraftAnswers } from "@/features/conversations/hooks/use-draft-answers";
import { useLearningSettingsTool } from "@/features/settings/hooks/use-learning-settings-tool";
import { useThemeTool } from "@/features/settings/hooks/use-theme-tool";
import { useAgentEventLog } from "@/hooks/use-agent-event-log";
import { useDisplay } from "@/hooks/use-display";
import { useDisplayContext } from "@/hooks/use-display-context";
import { useLayoutTool } from "@/hooks/use-layout-tool";
import { useLearningAgent } from "@/hooks/use-learning-agent";

/**
 * Registers the hooks that need the CopilotKit provider, once for the app.
 * `Workspace` never unmounts, so the tool renderers, the display tools and
 * the dev event log stay registered.
 */
export const useWorkspace = () => {
  const { state } = useLearningAgent();
  const display = useDisplay();
  const panelsRef = useRef<HTMLDivElement>(null);

  useToolRenderers();
  useStageSuggestions(state.stage);
  useThemeTool();
  useLayoutTool();
  useLearningSettingsTool();
  useChatUiTools();
  useDisplayContext();
  useAgentEventLog();
  useConversationRefresh();
  useConversationTitle();
  useRetakeFromHistory();
  useDraftAnswers();

  return { display, panelsRef };
};
