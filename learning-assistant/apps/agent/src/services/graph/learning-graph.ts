import { copilotkitMiddleware } from "@copilotkit/sdk-js/langgraph";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { BaseCheckpointSaver } from "@langchain/langgraph";
import { createAgent } from "langchain";

import {
  LearningGraphStateSchema,
  RunContextSchema,
} from "../../schemas/graph";
import { SUPERVISOR_PROMPT } from "../prompts/supervisor";
import { supervisorContextMiddleware } from "./supervisor-context";

interface LearningGraphOptions {
  /** The Supervisor's model, already holding the user's API key. */
  model: BaseChatModel;
  /** Keeps each thread's messages and state between runs. */
  checkpointer: BaseCheckpointSaver;
}

/**
 * The Supervisor as a LangChain agent. It is built for each request, because
 * the model carries that user's API key; threads live in the shared
 * `checkpointer`. `copilotkitMiddleware` offers the run's frontend tools to
 * the model and ends the run when one is called, so the browser can run it.
 */
export const createLearningGraph = ({
  model,
  checkpointer,
}: LearningGraphOptions) =>
  createAgent({
    model,
    tools: [],
    systemPrompt: SUPERVISOR_PROMPT,
    stateSchema: LearningGraphStateSchema,
    contextSchema: RunContextSchema,
    middleware: [copilotkitMiddleware, supervisorContextMiddleware],
    checkpointer,
  });

export type LearningGraph = ReturnType<typeof createLearningGraph>;
