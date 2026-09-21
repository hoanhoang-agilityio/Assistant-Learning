import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
} from "@copilotkit/runtime/v2";
import {
  FEEDBACK_CATALOG,
  FEEDBACK_CATALOG_ID,
} from "@repo/shared/a2ui/feedback-catalog";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";

import { SUPERVISOR_PROMPT } from "../../../../services/agents/prompts/supervisor";
import { LearningSupervisorAgent } from "../../../../services/agents/supervisor-agent";
import { stubResearchTool } from "../../../../services/agents/tools/stub-research";

const learningAgent = new LearningSupervisorAgent({
  prompt: SUPERVISOR_PROMPT,
  // TODO(M3.3): replace the stub with the real subagent tools.
  tools: () => [stubResearchTool],
});

const runtime = new CopilotRuntime({
  agents: { [LEARNING_AGENT_ID]: learningAgent },
  a2ui: {
    agents: [LEARNING_AGENT_ID],
    injectA2UITool: true,
    schema: FEEDBACK_CATALOG,
    defaultCatalogId: FEEDBACK_CATALOG_ID,
  },
});

const handler = createCopilotRuntimeHandler({
  runtime,
  basePath: "/api/copilotkit",
});

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const DELETE = handler;
