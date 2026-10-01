import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
} from "@copilotkit/runtime/v2";
import { createLearningAgent, LearningThreadRunner } from "@repo/agent";
import { getThreadCheckpointer } from "@repo/db";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";

import {
  COPILOT_RUNTIME_URL,
  FORWARD_HEADERS_POLICY,
  IS_DEVELOPMENT,
} from "@/constants/copilot";
import { readApiKeyFromRequest } from "@/features/api-key/services/request-api-key";
import { conversationOwners } from "@/features/conversations/services/conversation-owners";
import { conversationRecords } from "@/features/conversations/services/conversation-records";
import { createThreadGuardHooks } from "@/features/conversations/services/runtime-thread-guard";
import {
  createUnauthorizedResponse,
  getSignedInUserId,
  withSignedInUser,
} from "@/services/auth";
import { runRateLimiter } from "@/services/rate-limit";

const runtime = new CopilotRuntime({
  // Built per request so each run uses the caller's own OpenAI key, sent
  // sealed in a header and opened only here on the server, and the user id
  // from the Clerk session, never one the client sent. The agent runs its
  // LangChain graph in this process; threads are kept in Postgres, and each
  // run and completed stage is recorded with its conversation.
  agents: async ({ request }) => {
    const userId = await getSignedInUserId();
    if (!userId) {
      throw createUnauthorizedResponse();
    }
    return {
      [LEARNING_AGENT_ID]: createLearningAgent({
        apiKey: readApiKeyFromRequest(request),
        userId,
        checkpointer: getThreadCheckpointer(),
        records: conversationRecords,
      }),
    };
  },
  // Reload rebuilds a thread from its checkpoint when the runtime holds no
  // events for it.
  runner: new LearningThreadRunner(getThreadCheckpointer()),
  forwardHeaders: FORWARD_HEADERS_POLICY,
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
  // Each thread is a conversation, and only its owner may reach it.
  hooks: createThreadGuardHooks({
    getUserId: getSignedInUserId,
    owners: conversationOwners,
    runLimiter: runRateLimiter,
  }),
});

/** Every runtime endpoint (run, connect, stop, info, threads) needs a signed-in user. */
const handler = withSignedInUser(handleRuntime);

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const DELETE = handler;
