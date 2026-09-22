import {
  initialLearningState,
  type LearningState,
  type NewTopicDecision,
  NewTopicDecisionSchema,
} from "@repo/shared/schemas";

import { CURRENT_TOPIC_FALLBACK } from "@/features/chat/constants/new-topic";
import { hasQuizData } from "@/utils/learning-state";

/** Notes or a quiz exist, so a new topic would throw work away. */
export const hasTopicWork = (state: LearningState): boolean =>
  state.notes !== null || hasQuizData(state);

/**
 * The state after the student confirms a new topic: every stage is cleared.
 * The chat is not part of the state, so its history stays.
 */
export const resetForNewTopic = (): LearningState => initialLearningState;

/** What the card tells the Supervisor the student chose. */
export const createNewTopicDecision = (
  isConfirmed: boolean,
  topic: string,
  currentTopic: string | null,
): NewTopicDecision =>
  isConfirmed
    ? {
        confirmed: true,
        instruction: `The student confirmed. The canvas is cleared; call research with topic "${topic}" now.`,
      }
    : {
        confirmed: false,
        instruction: `The student kept working on ${
          currentTopic ? `"${currentTopic}"` : CURRENT_TOPIC_FALLBACK
        }. Do not call research; ask what they want to do next with it.`,
      };

/** The decision in a finished confirmation's result, or `null`. */
export const parseNewTopicDecision = (
  result: string | undefined,
): NewTopicDecision | null => {
  if (!result) {
    return null;
  }
  try {
    const parsed = NewTopicDecisionSchema.safeParse(JSON.parse(result));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
};
