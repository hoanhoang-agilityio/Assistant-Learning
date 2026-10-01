import type { AbstractAgent } from "@ag-ui/client";
import { LangGraphAgent, type LangGraphAgentConfig } from "@ag-ui/langgraph";
import type { BaseCheckpointSaver } from "@langchain/langgraph";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";

import { MISSING_API_KEY_ERROR } from "../../constants/errors";
import { IN_PROCESS_DEPLOYMENT_URL } from "../../constants/graph";
import type { LearningRecords } from "../../types/records";
import { createChatModel } from "../llm/chat-model";
import { toClientEvents } from "./client-events";
import { createInProcessClient } from "./in-process-client";
import { createLearningGraph, type LearningGraph } from "./learning-graph";
import { UnavailableAgent } from "./unavailable-agent";

interface LearningAgentOptions {
  /** The user's OpenAI API key for this request, opened from its sealed header. */
  apiKey?: string;
  /** The signed-in user's id, from the verified session. */
  userId: string;
  /** Where threads are kept. */
  checkpointer: BaseCheckpointSaver;
  /** Where each conversation's runs and completed stages are kept. */
  records: LearningRecords;
}

/**
 * `LangGraphAgent` over a graph in this process. The in-process client
 * stands in for the LangGraph SDK client (it implements the methods the
 * adapter calls), and everything the adapter emits is cut down to what the
 * browser may receive.
 */
export const createGraphAgent = (
  graph: LearningGraph,
  userId: string,
  records: LearningRecords,
): LangGraphAgent => {
  const client = createInProcessClient({ graph, userId, records });
  const agent = new LangGraphAgent({
    graphId: LEARNING_AGENT_ID,
    deploymentUrl: IN_PROCESS_DEPLOYMENT_URL,
    client: client as unknown as LangGraphAgentConfig["client"],
  });
  agent.use((input, next) =>
    next.run(input).pipe(toClientEvents(input.messages)),
  );
  return agent;
};

/**
 * The learning agent for one request: the Supervisor graph with a model that
 * holds the caller's own OpenAI key, run in this process for `userId`.
 * Without a key it is an agent whose runs say how to add one.
 */
export const createLearningAgent = ({
  apiKey,
  userId,
  checkpointer,
  records,
}: LearningAgentOptions): AbstractAgent => {
  const trimmedKey = apiKey?.trim();
  if (!trimmedKey) {
    return new UnavailableAgent(MISSING_API_KEY_ERROR);
  }

  const graph = createLearningGraph({
    model: createChatModel(trimmedKey),
    apiKey: trimmedKey,
    checkpointer,
    records,
  });
  return createGraphAgent(graph, userId, records);
};
