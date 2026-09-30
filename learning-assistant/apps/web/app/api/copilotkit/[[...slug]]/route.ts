import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
} from "@copilotkit/runtime/v2";
import {
  createLearningTools,
  LearningSupervisorAgent,
  SUPERVISOR_PROMPT,
} from "@repo/agent";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";

import { COPILOT_RUNTIME_URL, IS_DEVELOPMENT } from "@/constants/copilot";
import { readApiKeyFromRequest } from "@/features/api-key/services/request-api-key";
import { createThreadGuardHooks } from "@/features/threads/services/runtime-thread-guard";
import { threadOwnerStore } from "@/features/threads/services/thread-owners";
import { getSignedInUserId, withSignedInUser } from "@/services/auth";

const runtime = new CopilotRuntime({
  // Built per request so each run uses the caller's own OpenAI key, sent
  // sealed in a header and opened only here on the server, and the user id
  // from the Clerk session (the handler below already turned away anyone
  // signed out), never one the client sent.
  agents: async ({ request }) => ({
    [LEARNING_AGENT_ID]: new LearningSupervisorAgent({
      prompt: SUPERVISOR_PROMPT,
      tools: createLearningTools,
      apiKey: readApiKeyFromRequest(request),
      userId: (await getSignedInUserId()) ?? undefined,
    }),
  }),
  // The A2UI middleware delivers surface actions (the quiz Submit) to the
  // agent, and turns the `a2ui_operations` a chat `renderSurface` result
  // carries into a chat surface (Board results go to state instead). No
  // render tool is injected: the Supervisor's own `renderSurface` is typed
  // to the app's catalogs, and the Evaluator composes the Feedback surface
  // itself (`@repo/agent`'s `subagents/feedback-surface.ts`).
  a2ui: {
    agents: [LEARNING_AGENT_ID],
    injectA2UITool: false,
  },
  // Dev only, opt-in: logs every AG-UI event the runtime streams, one line
  // each, to the `next dev` terminal. Off by default because each token delta
  // is its own line.
  debug: IS_DEVELOPMENT && process.env.COPILOTKIT_DEBUG === "true",
});

const handleRuntime = createCopilotRuntimeHandler({
  runtime,
  basePath: COPILOT_RUNTIME_URL,
  // Each thread belongs to the user who started it.
  hooks: createThreadGuardHooks({
    getUserId: getSignedInUserId,
    owners: threadOwnerStore,
  }),
});

/** Every runtime endpoint (run, connect, stop, info, threads) needs a signed-in user. */
const handler = withSignedInUser(handleRuntime);

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const DELETE = handler;
