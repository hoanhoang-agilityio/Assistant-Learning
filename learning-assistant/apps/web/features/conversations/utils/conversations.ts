import type { ConversationSummary, LearningState } from "@repo/shared/schemas";

import {
  STAGE_LABELS,
  UNTITLED_TITLE,
} from "@/features/conversations/constants/conversations";
import type { ActiveConversation } from "@/features/conversations/types/conversations";

/** What the sidebar calls a conversation. */
export const getConversationTitle = ({ title }: ConversationSummary): string =>
  title ?? UNTITLED_TITLE;

/** The conversations whose title or topic contains `query`, ignoring case. */
export const filterConversations = (
  conversations: ConversationSummary[],
  query: string,
): ConversationSummary[] => {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return conversations;
  }
  return conversations.filter((conversation) =>
    [getConversationTitle(conversation), conversation.topic ?? ""].some(
      (text) => text.toLowerCase().includes(needle),
    ),
  );
};

/** A conversation the student has not written in yet: nothing to restore. */
export const isNewConversation = ({ title }: ConversationSummary): boolean =>
  title === null;

export const toActiveConversation = (
  conversation: ConversationSummary,
): ActiveConversation => ({
  id: conversation.id,
  isNew: isNewConversation(conversation),
});

/**
 * Which conversation to open on load: the one open last time if it is
 * still there, otherwise the most recent. `null` when there are none.
 */
export const pickConversation = (
  conversations: ConversationSummary[],
  savedId: string | undefined,
): ConversationSummary | null =>
  conversations.find(({ id }) => id === savedId) ?? conversations[0] ?? null;

/** Where to go when `id` is deleted: the most recent other conversation. */
export const pickNextConversation = (
  conversations: ConversationSummary[],
  id: string,
): ConversationSummary | null =>
  conversations.find((conversation) => conversation.id !== id) ?? null;

/**
 * What the resume banner says about a reopened conversation, e.g. "You were
 * on the Quiz stage, 3/5 answered." `null` when there is nothing to resume.
 */
export const formatResumeMessage = (state: LearningState): string | null => {
  if (state.stage === "idle") {
    return null;
  }

  const where = `You were on the ${STAGE_LABELS[state.stage]} stage`;
  const { quiz } = state;
  if (state.stage === "quiz" && quiz && !quiz.submitted) {
    const answered = Object.keys(quiz.answers).length;
    return `${where}, ${answered}/${quiz.questions.length} answered.`;
  }
  return `${where}.`;
};

/** The score badge: "67% · Practitioner". */
export const formatScore = ({
  percent,
  tier,
}: NonNullable<ConversationSummary["score"]>): string =>
  `${Math.round(percent)}% · ${tier}`;
