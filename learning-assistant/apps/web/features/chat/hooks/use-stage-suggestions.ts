import { useConfigureSuggestions } from "@copilotkit/react-core/v2";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";
import type { Stage } from "@repo/shared/schemas";

import { STAGE_SUGGESTIONS } from "@/features/chat/constants/suggestions";

/**
 * Stage-aware quick prompts. Shown after every reply ("always") because they
 * change with the stage and point to the next step, and kept to 1–3 pills.
 */
export const useStageSuggestions = (stage: Stage) => {
  useConfigureSuggestions(
    {
      suggestions: [...STAGE_SUGGESTIONS[stage]],
      available: "always",
      consumerAgentId: LEARNING_AGENT_ID,
    },
    [stage],
  );
};
