import type { Stage } from "@repo/shared/schemas";
import { useState } from "react";

import { useActiveConversation } from "@/features/conversations/hooks/use-conversation-store";
import { formatResumeMessage } from "@/features/conversations/utils/conversations";
import { useLearningAgent } from "@/hooks/use-learning-agent";

interface ResumePoint {
  conversationId: string;
  stage: Stage;
}

/**
 * What the resume banner says when a conversation is reopened: the stage it
 * was left on, and how far a quiz got. It goes once the student dismisses
 * it or moves to another stage. A new conversation has nothing to resume.
 */
export const useResumeBanner = () => {
  const active = useActiveConversation();
  const { state } = useLearningAgent();
  const [resumePoint, setResumePoint] = useState<ResumePoint | null>(null);
  const [dismissedId, setDismissedId] = useState<string | null>(null);

  const isReopened = active !== null && !active.isNew;
  // The first stage the restored state shows is where the student left off.
  if (
    isReopened &&
    state.stage !== "idle" &&
    resumePoint?.conversationId !== active.id
  ) {
    setResumePoint({ conversationId: active.id, stage: state.stage });
  }

  const isShown =
    isReopened &&
    dismissedId !== active.id &&
    resumePoint?.conversationId === active.id &&
    resumePoint.stage === state.stage;

  return {
    message: isShown ? formatResumeMessage(state) : null,
    handleDismiss: () => setDismissedId(active?.id ?? null),
  };
};
