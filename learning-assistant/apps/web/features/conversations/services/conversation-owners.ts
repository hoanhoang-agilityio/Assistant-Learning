import {
  filterOwnedConversationIds,
  findConversationOwner,
  getDatabase,
} from "@repo/db";

import type { ThreadOwners } from "@/features/conversations/types/threads";

/** Thread owners from the `conversations` table: a thread is a conversation. */
export const conversationOwners: ThreadOwners = {
  getOwner: (threadId) => findConversationOwner(getDatabase(), threadId),
  filterOwned: (userId, threadIds) =>
    filterOwnedConversationIds(getDatabase(), userId, threadIds),
};
