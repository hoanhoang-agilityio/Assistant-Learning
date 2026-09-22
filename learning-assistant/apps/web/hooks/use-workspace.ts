import { useRef } from "react";

import { useNewTopicTool } from "@/features/chat/hooks/use-new-topic-tool";
import { useStageSuggestions } from "@/features/chat/hooks/use-stage-suggestions";
import { useToolRenderers } from "@/features/chat/hooks/use-tool-renderers";
import { hasTopicWork } from "@/features/chat/utils/new-topic";
import { useLayout } from "@/hooks/use-layout-store";
import { useLearningAgent } from "@/hooks/use-learning-agent";

/**
 * Registers the hooks that need the CopilotKit provider, once for the app.
 * `Workspace` never unmounts, so the tool renderers and the new-topic
 * confirmation stay registered.
 */
export const useWorkspace = () => {
  const { state } = useLearningAgent();
  const { isChatOpen } = useLayout();
  const panelsRef = useRef<HTMLDivElement>(null);

  useToolRenderers();
  useNewTopicTool(hasTopicWork(state));
  useStageSuggestions(state.stage);

  return { isChatOpen, panelsRef };
};
