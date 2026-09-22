import { useState } from "react";

import {
  createNewTopicDecision,
  parseNewTopicDecision,
  resetForNewTopic,
} from "@/features/chat/utils/new-topic";
import { useLearningAgent } from "@/hooks/use-learning-agent";

/**
 * The new-topic card's choice. Confirm clears the canvas first, so the run
 * that follows starts from an empty state; both choices answer the tool call,
 * which resumes the Supervisor. A card answers once.
 */
export const useNewTopicCard = (
  topic: string | undefined,
  respond: ((result: unknown) => Promise<void>) | undefined,
  result: string | undefined,
) => {
  const { agent, state } = useLearningAgent();
  const [isAnswered, setIsAnswered] = useState(false);
  const decision = parseNewTopicDecision(result);

  const answer = (isConfirmed: boolean) => {
    if (!respond || !topic || isAnswered) {
      return;
    }
    setIsAnswered(true);

    if (isConfirmed) {
      agent.setState(resetForNewTopic());
    }
    const next = createNewTopicDecision(isConfirmed, topic, state.topic);
    respond(JSON.stringify(next)).catch((error: unknown) => {
      console.error("[chat] Answering the new-topic card failed", error);
    });
  };

  return {
    currentTopic: state.topic,
    decision,
    canAnswer: respond !== undefined && topic !== undefined && !isAnswered,
    handleConfirm: () => answer(true),
    handleKeep: () => answer(false),
  };
};
