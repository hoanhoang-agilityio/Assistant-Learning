import {
  ConversationListSchema,
  type ConversationSummary,
  ConversationSummarySchema,
  type DraftAnswers,
  DraftAnswersSchema,
} from "@repo/shared/schemas";
import { z } from "zod";

import {
  CONVERSATION_ANSWERS_SEGMENT,
  CONVERSATIONS_API_PATH,
} from "@/features/conversations/constants/conversations";
import { expectOk } from "@/services/expect-ok";

const toConversationPath = (id: string) =>
  `${CONVERSATIONS_API_PATH}/${encodeURIComponent(id)}`;

const toAnswersPath = (id: string) =>
  `${toConversationPath(id)}/${CONVERSATION_ANSWERS_SEGMENT}`;

const SavedDraftSchema = z.object({ draft: DraftAnswersSchema.nullable() });

/** The signed-in user's conversations, most recent first. */
export const fetchConversations = async (): Promise<ConversationSummary[]> => {
  const response = await expectOk(await fetch(CONVERSATIONS_API_PATH));
  return ConversationListSchema.parse(await response.json()).conversations;
};

/** A conversation for a new topic: the one not started yet, if there is one. */
export const createConversation = async (): Promise<ConversationSummary> => {
  const response = await expectOk(
    await fetch(CONVERSATIONS_API_PATH, { method: "POST" }),
  );
  return ConversationSummarySchema.parse(await response.json());
};

export const updateConversationTitle = async (
  id: string,
  title: string,
): Promise<ConversationSummary> => {
  const response = await expectOk(
    await fetch(toConversationPath(id), {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title }),
    }),
  );
  return ConversationSummarySchema.parse(await response.json());
};

export const deleteConversation = async (id: string): Promise<void> => {
  await expectOk(await fetch(toConversationPath(id), { method: "DELETE" }));
};

/** The answers kept for the conversation's quiz, or `null`. */
export const fetchDraftAnswers = async (
  id: string,
): Promise<DraftAnswers | null> => {
  const response = await expectOk(await fetch(toAnswersPath(id)));
  return SavedDraftSchema.parse(await response.json()).draft;
};

export const saveDraftAnswers = async (
  id: string,
  draft: DraftAnswers,
): Promise<void> => {
  await expectOk(
    await fetch(toAnswersPath(id), {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(draft),
    }),
  );
};
