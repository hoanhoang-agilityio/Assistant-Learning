import type { Reflection } from "@repo/shared/schemas";
import { useState } from "react";

import { useSendMessage } from "@/features/canvas/hooks/use-send-message";
import {
  formatReflectionMessage,
  toReflection,
} from "@/features/canvas/utils/feedback";
import { useLearningAgent } from "@/hooks/use-learning-agent";
import { readLearningState } from "@/utils/learning-state";

/**
 * The reflection form. Saving writes `reflection` to the agent's state, then
 * posts it to the chat so the assistant can respond. A saved reflection shows
 * as a confirmation until the student chooses to edit it.
 */
export const useReflectionForm = (saved: Reflection | null) => {
  const { agent, isRunning } = useLearningAgent();
  const sendMessage = useSendMessage();
  const [rating, setRating] = useState(saved?.rating ?? 0);
  const [text, setText] = useState(saved?.text ?? "");
  const [isEditing, setIsEditing] = useState(saved === null);
  const reflection = toReflection({ rating, text });

  const handleSubmit = () => {
    if (!reflection || agent.isRunning) {
      return;
    }
    agent.setState({ ...readLearningState(agent.state), reflection });
    sendMessage(formatReflectionMessage(reflection));
    setIsEditing(false);
  };

  return {
    rating,
    text,
    isSaved: saved !== null && !isEditing,
    canSubmit: reflection !== null && !isRunning,
    isLocked: isRunning,
    handleRatingChange: setRating,
    handleTextChange: setText,
    handleSubmit,
    handleEdit: () => setIsEditing(true),
  };
};
