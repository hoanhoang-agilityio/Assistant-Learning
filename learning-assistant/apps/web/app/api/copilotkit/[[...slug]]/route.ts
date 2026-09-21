import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
} from "@copilotkit/runtime/v2";
import {
  FEEDBACK_CATALOG,
  FEEDBACK_CATALOG_ID,
} from "@repo/shared/a2ui/feedback-catalog";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";

import { COPILOT_RUNTIME_URL } from "@/constants/copilot";
import { SUPERVISOR_PROMPT } from "@/features/agent/services/prompts/supervisor";
import { LearningSupervisorAgent } from "@/features/agent/services/supervisor-agent";
import { createLearningTools } from "@/features/agent/services/tools/learning-tools";

const learningAgent = new LearningSupervisorAgent({
  prompt: SUPERVISOR_PROMPT,
  // TODO(M4.3, M5): add the generateQuiz and evaluate tools.
  tools: createLearningTools,
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
  basePath: COPILOT_RUNTIME_URL,
});

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const DELETE = handler;
