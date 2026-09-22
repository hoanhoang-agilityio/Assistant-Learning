"use client";

import { NewTopicCardView } from "@/features/chat/components/NewTopicCardView";
import { useNewTopicCard } from "@/features/chat/hooks/use-new-topic-card";
import type { ToolCallStatus } from "@/features/chat/types/chat";

export interface NewTopicCardProps {
  /** The new topic; missing while the tool call still streams. */
  topic?: string;
  status: ToolCallStatus;
  /** Answers the tool call; set only while it waits for the student. */
  respond?: (result: unknown) => Promise<void>;
  result?: string;
}

/** Asks the student to confirm a new topic before the canvas is cleared. */
export const NewTopicCard = ({
  topic,
  status,
  respond,
  result,
}: NewTopicCardProps) => {
  const { currentTopic, decision, canAnswer, handleConfirm, handleKeep } =
    useNewTopicCard(topic, respond, result);

  return (
    <NewTopicCardView
      topic={topic}
      currentTopic={currentTopic}
      isPreparing={status === "inProgress"}
      isConfirmed={decision?.confirmed ?? null}
      canAnswer={canAnswer}
      onConfirm={handleConfirm}
      onKeep={handleKeep}
    />
  );
};
