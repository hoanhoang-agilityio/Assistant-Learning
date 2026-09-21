import { useRef } from "react";

import { useStageSuggestions } from "@/features/chat/hooks/use-stage-suggestions";
import { useToolRenderers } from "@/features/chat/hooks/use-tool-renderers";
import { useLayout } from "@/hooks/use-layout-store";
import { useLearningAgent } from "@/hooks/use-learning-agent";

/**
 * Registers the hooks that need the CopilotKit provider, once for the app.
 * `Workspace` never unmounts, so the tool renderers stay registered.
 */
export const useWorkspace = () => {
  const { state } = useLearningAgent();
  const { isChatOpen } = useLayout();
  const panelsRef = useRef<HTMLDivElement>(null);

  useToolRenderers();
  useStageSuggestions(state.stage);

  return { isChatOpen, panelsRef };
};
