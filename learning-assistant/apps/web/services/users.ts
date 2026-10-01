import { currentUser } from "@clerk/nextjs/server";
import { ensureUser, getDatabase } from "@repo/db";

import { USER_ROWS_GLOBAL_KEY } from "@/constants/users";

const globalRows = globalThis as typeof globalThis & {
  [USER_ROWS_GLOBAL_KEY]?: Map<string, string>;
};

/** Clerk id → `users.id`, so only a user's first request touches the table. */
const userRows = (globalRows[USER_ROWS_GLOBAL_KEY] ??= new Map());

const getPrimaryEmail = async (): Promise<string | null> =>
  (await currentUser())?.primaryEmailAddress?.emailAddress ?? null;

/**
 * The signed-in user's row id. The row is created on their first request,
 * with the email Clerk has for them.
 */
export const getUserRowId = async (clerkUserId: string): Promise<string> => {
  const known = userRows.get(clerkUserId);
  if (known) {
    return known;
  }

  const id = await ensureUser(getDatabase(), {
    clerkUserId,
    getEmail: getPrimaryEmail,
  });
  userRows.set(clerkUserId, id);
  return id;
};

/** Forgets a deleted user, so a later request makes a new row. */
export const forgetUserRow = (clerkUserId: string): void => {
  userRows.delete(clerkUserId);
};
