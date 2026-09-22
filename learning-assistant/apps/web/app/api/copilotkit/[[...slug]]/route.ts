import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
} from "@copilotkit/runtime/v2";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";

import { COPILOT_RUNTIME_URL } from "@/constants/copilot";
import { SUPERVISOR_PROMPT } from "@/features/agent/services/prompts/supervisor";
import { LearningSupervisorAgent } from "@/features/agent/services/supervisor-agent";
import { createLearningTools } from "@/features/agent/services/tools/learning-tools";
import { readApiKeyFromRequest } from "@/features/api-key/services/request-api-key";

const runtime = new CopilotRuntime({
  // Built per request so each run uses the caller's own OpenAI key, sent
  // sealed in a header and opened only here on the server.
  agents: ({ request }) => ({
    [LEARNING_AGENT_ID]: new LearningSupervisorAgent({
      prompt: SUPERVISOR_PROMPT,
      tools: createLearningTools,
      apiKey: readApiKeyFromRequest(request),
    }),
  }),
  // The A2UI middleware delivers surface actions (the quiz Submit) to the
  // agent. The Supervisor gets no render tool: the Evaluator composes the
  // Feedback surface itself (`subagents/feedback-surface.ts`), so the
  // Feedback catalog is not injected into the Supervisor's context either.
  a2ui: {
    agents: [LEARNING_AGENT_ID],
    injectA2UITool: false,
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
