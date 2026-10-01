import { eq } from "drizzle-orm";

import type { Database } from "../client";
import { conversations, users } from "../schema";

interface EnsureUserInput {
  clerkUserId: string;
  /** Asked only when the row is created. */
  getEmail: () => Promise<string | null>;
}

const findUserId = async (
  db: Database,
  clerkUserId: string,
): Promise<string | undefined> => {
  const [row] = await db
    .select({ id: users.id })
    .from(users)
    .where(eq(users.clerkUserId, clerkUserId));
  return row?.id;
};

/** The user's row id, creating the row on their first request. */
export const ensureUser = async (
  db: Database,
  { clerkUserId, getEmail }: EnsureUserInput,
): Promise<string> => {
  const existing = await findUserId(db, clerkUserId);
  if (existing) {
    return existing;
  }

  const email = await getEmail();
  const [created] = await db
    .insert(users)
    .values({ clerkUserId, email })
    .onConflictDoNothing({ target: users.clerkUserId })
    .returning({ id: users.id });
  // Another request created it first.
  const id = created?.id ?? (await findUserId(db, clerkUserId));
  if (!id) {
    throw new Error(`User ${clerkUserId} could not be created`);
  }
  return id;
};

/** The user's conversation ids: the threads to delete with them. */
export const listUserConversationIds = async (
  db: Database,
  clerkUserId: string,
): Promise<string[]> => {
  const rows = await db
    .select({ id: conversations.id })
    .from(conversations)
    .innerJoin(users, eq(users.id, conversations.userId))
    .where(eq(users.clerkUserId, clerkUserId));
  return rows.map(({ id }) => id);
};

/** Deletes the user and, by cascade, all their rows. False when there was none. */
export const deleteUser = async (
  db: Database,
  clerkUserId: string,
): Promise<boolean> => {
  const deleted = await db
    .delete(users)
    .where(eq(users.clerkUserId, clerkUserId))
    .returning({ id: users.id });
  return deleted.length > 0;
};
