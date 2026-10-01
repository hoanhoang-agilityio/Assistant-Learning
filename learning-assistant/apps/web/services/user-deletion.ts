import {
  deleteUser,
  getDatabase,
  getThreadCheckpointer,
  listUserConversationIds,
} from "@repo/db";

import { forgetUserRow } from "@/services/users";

/**
 * Removes a user who was deleted in Clerk: every conversation's thread
 * checkpoints, then their row, which cascades to their settings,
 * conversations and everything in them.
 */
export const deleteUserData = async (clerkUserId: string): Promise<void> => {
  const db = getDatabase();
  const checkpointer = getThreadCheckpointer();
  for (const threadId of await listUserConversationIds(db, clerkUserId)) {
    await checkpointer.deleteThread(threadId);
  }

  await deleteUser(db, clerkUserId);
  forgetUserRow(clerkUserId);
};
