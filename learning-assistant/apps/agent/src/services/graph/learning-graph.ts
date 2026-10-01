import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { BaseCheckpointSaver } from "@langchain/langgraph";
import {
  createAgent,
  modelCallLimitMiddleware,
  toolErrorMiddleware,
} from "langchain";

import { SUPERVISOR_MAX_STEPS } from "../../constants/agents";
import {
  LearningGraphStateSchema,
  RunContextSchema,
} from "../../schemas/graph";
import type { LearningRecords } from "../../types/records";
import { getErrorMessage } from "../../utils/openai-errors";
import { SUPERVISOR_PROMPT } from "../prompts/supervisor";
import { createConversationSummaryMiddleware } from "./conversation-summary";
import { frontendToolsMiddleware } from "./frontend-tools";
import { quizSubmitMiddleware } from "./quiz-submit";
import { supervisorContextMiddleware } from "./supervisor-context";
import { createSubagentTools } from "./tools/subagent-tools";
import { createSurfaceTools } from "./tools/surface-tools";

interface LearningGraphOptions {
  /** The Supervisor's model, already holding the user's API key. */
  model: BaseChatModel;
  /** The user's OpenAI API key, for the subagents' own model calls. */
  apiKey: string;
  /** Keeps each thread's messages and state between runs. */
  checkpointer: BaseCheckpointSaver;
  /** Keeps each completed stage with its conversation. */
  records: LearningRecords;
}

/** A tool call that threw instead of returning: bad arguments or an unknown tool. */
const toToolFailure = (error: unknown): string =>
  JSON.stringify({ ok: false, error: getErrorMessage(error) });

/**
 * The Supervisor as a LangChain agent, with the subagent tools and the tools
 * that draw in the chat and on the Board. It is built for each request,
 * because the model and the subagent tools carry that user's API key;
 * threads live in the shared `checkpointer`.
 *
 * The middleware, in order: a cap on model calls in one run, which ends the
 * run rather than failing it; a failed tool call answered with an error the
 * Supervisor can explain, instead of failing the run; the run's frontend
 * tools, offered to the model, ending the run when one is called so the
 * browser can run it; the quiz Submit; what the Supervisor reads on each
 * call; and, after the turn, the summary of the conversation's older
 * messages.
 */
export const createLearningGraph = ({
  model,
  apiKey,
  checkpointer,
  records,
}: LearningGraphOptions) =>
  createAgent({
    model,
    tools: [
      ...createSubagentTools({ apiKey, records }),
      ...createSurfaceTools(),
    ],
    systemPrompt: SUPERVISOR_PROMPT,
    stateSchema: LearningGraphStateSchema,
    contextSchema: RunContextSchema,
    middleware: [
      modelCallLimitMiddleware({
        runLimit: SUPERVISOR_MAX_STEPS,
        exitBehavior: "end",
      }),
      toolErrorMiddleware({ onError: toToolFailure }),
      frontendToolsMiddleware,
      quizSubmitMiddleware,
      supervisorContextMiddleware,
      createConversationSummaryMiddleware(apiKey),
    ],
    checkpointer,
  });

export type LearningGraph = ReturnType<typeof createLearningGraph>;
