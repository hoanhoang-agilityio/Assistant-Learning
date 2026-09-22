"use client";

import { FeedbackReadyCardView } from "@/features/chat/components/FeedbackReadyCardView";
import { useFeedbackReadyCard } from "@/features/chat/hooks/use-feedback-ready-card";

export interface FeedbackReadyCardProps {
  /** The `evaluate` tool result. */
  result?: string;
}

/** "Feedback ready →" in the chat, once the quiz is graded. */
export const FeedbackReadyCard = ({ result }: FeedbackReadyCardProps) => {
  const { score, isVisible, handleOpen } = useFeedbackReadyCard(result);
  if (!isVisible || !score) {
    return null;
  }

  return <FeedbackReadyCardView score={score} onOpen={handleOpen} />;
};
