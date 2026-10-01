import {
  ConversationListSchema,
  type ConversationSummary,
  ConversationSummarySchema,
} from "@repo/shared/schemas";

import { CONVERSATIONS_API_PATH } from "@/features/conversations/constants/conversations";

const toConversationPath = (id: string) =>
  `${CONVERSATIONS_API_PATH}/${encodeURIComponent(id)}`;

/** The response, or an error with the server's message. */
const expectOk = async (response: Response): Promise<Response> => {
  if (response.ok) {
    return response;
  }

  let message = `Request failed (${response.status})`;
  try {
    const body = (await response.json()) as { error?: unknown };
    if (typeof body.error === "string") {
      message = body.error;
    }
  } catch {
    // Keep the status message.
  }
  throw new Error(message);
};

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
