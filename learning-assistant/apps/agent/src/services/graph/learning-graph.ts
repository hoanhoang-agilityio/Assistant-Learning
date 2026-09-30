import { copilotkitMiddleware } from "@copilotkit/sdk-js/langgraph";
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
import { getErrorMessage } from "../../utils/openai-errors";
import { SUPERVISOR_PROMPT } from "../prompts/supervisor";
import { quizSubmitMiddleware } from "./quiz-submit";
import { supervisorContextMiddleware } from "./supervisor-context";
import { createSubagentTools } from "./tools/subagent-tools";

interface LearningGraphOptions {
  /** The Supervisor's model, already holding the user's API key. */
  model: BaseChatModel;
  /** The user's OpenAI API key, for the subagents' own model calls. */
  apiKey: string;
  /** Keeps each thread's messages and state between runs. */
  checkpointer: BaseCheckpointSaver;
}

/** A tool call that threw instead of returning: bad arguments or an unknown tool. */
const toToolFailure = (error: unknown): string =>
  JSON.stringify({ ok: false, error: getErrorMessage(error) });

/**
 * The Supervisor as a LangChain agent. It is built for each request, because
 * the model and the subagent tools carry that user's API key; threads live
 * in the shared `checkpointer`.
 *
 * The middleware, in order: a cap on model calls in one run, which ends the
 * run rather than failing it; a failed tool call answered with an error the
 * Supervisor can explain, instead of failing the run; `copilotkitMiddleware`,
 * which offers the run's frontend tools to the model and ends the run when
 * one is called, so the browser can run it; the quiz Submit; and what the
 * Supervisor reads on each call.
 */
export const createLearningGraph = ({
  model,
  apiKey,
  checkpointer,
}: LearningGraphOptions) =>
  createAgent({
    model,
    tools: createSubagentTools({ apiKey }),
    systemPrompt: SUPERVISOR_PROMPT,
    stateSchema: LearningGraphStateSchema,
    contextSchema: RunContextSchema,
    middleware: [
      modelCallLimitMiddleware({
        runLimit: SUPERVISOR_MAX_STEPS,
        exitBehavior: "end",
      }),
      toolErrorMiddleware({ onError: toToolFailure }),
      copilotkitMiddleware,
      quizSubmitMiddleware,
      supervisorContextMiddleware,
    ],
    checkpointer,
  });

export type LearningGraph = ReturnType<typeof createLearningGraph>;
