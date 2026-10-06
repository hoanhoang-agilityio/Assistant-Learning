import type { ConversationSummary, Stage } from "@repo/shared/schemas";
import {
  createAutoTitle,
  getConversationStatus,
  getStoredStatus,
} from "@repo/shared/utils/conversations";
import { and, desc, eq, inArray, isNull, or, sql } from "drizzle-orm";
import { z } from "zod";

import type { Database } from "../client";
import { conversations, quizAttempts, users } from "../schema";
import { recomputeConceptMemories } from "./memory";

type ConversationRow = typeof conversations.$inferSelect;

interface LatestScore {
  percent: number;
  tier: NonNullable<(typeof quizAttempts.$inferSelect)["tier"]>;
}

/** Thread ids come from the browser: anything but a uuid names no conversation. */
const isConversationId = (id: string): boolean =>
  z.uuid().safeParse(id).success;

const toSummary = (
  row: ConversationRow,
  score: LatestScore | null,
  now: Date,
): ConversationSummary => ({
  id: row.id,
  title: row.title,
  topic: row.topic,
  stage: row.stage,
  status: getConversationStatus(row.status, row.lastActivityAt, now),
  score,
  lastActivityAt: row.lastActivityAt.toISOString(),
  createdAt: row.createdAt.toISOString(),
});

/** Each conversation's latest graded score. */
const findLatestScores = async (
  db: Database,
  ids: string[],
): Promise<Map<string, LatestScore>> => {
  if (ids.length === 0) {
    return new Map();
  }

  const rows = await db
    .select({
      conversationId: quizAttempts.conversationId,
      scorePct: quizAttempts.scorePct,
      tier: quizAttempts.tier,
    })
    .from(quizAttempts)
    .where(
      and(
        inArray(quizAttempts.conversationId, ids),
        eq(quizAttempts.status, "submitted"),
      ),
    )
    .orderBy(desc(quizAttempts.attemptNo));
  const scores = new Map<string, LatestScore>();
  for (const { conversationId, scorePct, tier } of rows) {
    if (!scores.has(conversationId) && scorePct !== null && tier !== null) {
      scores.set(conversationId, { percent: scorePct, tier });
    }
  }
  return scores;
};

const summarize = async (
  db: Database,
  rows: ConversationRow[],
  now: Date,
): Promise<ConversationSummary[]> => {
  const scores = await findLatestScores(
    db,
    rows.map(({ id }) => id),
  );
  return rows.map((row) => toSummary(row, scores.get(row.id) ?? null, now));
};

/** The user's conversations, most recently active first. */
export const listConversations = async (
  db: Database,
  userId: string,
  now = new Date(),
): Promise<ConversationSummary[]> => {
  const rows = await db
    .select()
    .from(conversations)
    .where(eq(conversations.userId, userId))
    .orderBy(desc(conversations.lastActivityAt));
  return summarize(db, rows, now);
};

/** One of the user's conversations, or `null` when it is not theirs. */
export const getConversation = async (
  db: Database,
  userId: string,
  id: string,
  now = new Date(),
): Promise<ConversationSummary | null> => {
  if (!isConversationId(id)) {
    return null;
  }

  const rows = await db
    .select()
    .from(conversations)
    .where(and(eq(conversations.id, id), eq(conversations.userId, userId)));
  const [summary] = await summarize(db, rows, now);
  return summary ?? null;
};

/**
 * A conversation for a new topic. A user keeps at most one that has not
 * started (no title yet): it is reused, so pressing "New topic" twice does
 * not leave an empty one behind.
 */
export const createConversation = async (
  db: Database,
  userId: string,
  now = new Date(),
): Promise<ConversationSummary> => {
  const [unstarted] = await db
    .update(conversations)
    .set({ lastActivityAt: now })
    .where(and(eq(conversations.userId, userId), isNull(conversations.title)))
    .returning();
  const row =
    unstarted ??
    (
      await db
        .insert(conversations)
        .values({ userId, lastActivityAt: now, createdAt: now })
        .returning()
    )[0];
  if (!row) {
    throw new Error("The conversation could not be created");
  }
  return toSummary(row, null, now);
};

/** The Clerk id of the user who owns the thread, or `undefined` for none. */
export const findConversationOwner = async (
  db: Database,
  id: string,
): Promise<string | undefined> => {
  if (!isConversationId(id)) {
    return undefined;
  }

  const [row] = await db
    .select({ clerkUserId: users.clerkUserId })
    .from(conversations)
    .innerJoin(users, eq(users.id, conversations.userId))
    .where(eq(conversations.id, id));
  return row?.clerkUserId;
};

/** Which of `ids` the Clerk user owns. */
export const filterOwnedConversationIds = async (
  db: Database,
  clerkUserId: string,
  ids: string[],
): Promise<Set<string>> => {
  const valid = ids.filter(isConversationId);
  if (valid.length === 0) {
    return new Set();
  }

  const rows = await db
    .select({ id: conversations.id })
    .from(conversations)
    .innerJoin(users, eq(users.id, conversations.userId))
    .where(
      and(inArray(conversations.id, valid), eq(users.clerkUserId, clerkUserId)),
    );
  return new Set(rows.map(({ id }) => id));
};

/** The student's own name for the conversation; research no longer renames it. */
export const renameConversation = async (
  db: Database,
  userId: string,
  id: string,
  title: string,
  now = new Date(),
): Promise<ConversationSummary | null> => {
  if (!isConversationId(id)) {
    return null;
  }

  const rows = await db
    .update(conversations)
    .set({ title, isTitleCustom: true })
    .where(and(eq(conversations.id, id), eq(conversations.userId, userId)))
    .returning();
  const [summary] = await summarize(db, rows, now);
  return summary ?? null;
};

/**
 * Names the conversation by the title summarised from its first message,
 * unless it already has another name: one the student gave it, or the
 * research title. Its first message, cut short, is replaced, since that is
 * only what a run that ended first names it by. Returns the conversation
 * as it is now, or `null` when it is not theirs.
 */
export const saveSummarizedTitle = async (
  db: Database,
  userId: string,
  id: string,
  { title, message }: { title: string; message: string },
  now = new Date(),
): Promise<ConversationSummary | null> => {
  if (!isConversationId(id)) {
    return null;
  }

  await db
    .update(conversations)
    .set({ title })
    .where(
      and(
        eq(conversations.id, id),
        eq(conversations.userId, userId),
        eq(conversations.isTitleCustom, false),
        or(
          isNull(conversations.title),
          eq(conversations.title, createAutoTitle(message) ?? ""),
        ),
      ),
    );
  return getConversation(db, userId, id, now);
};

/**
 * Deletes the conversation and, by cascade, its rows and its topic in
 * memory; the student's concept mastery is rebuilt from the attempts that
 * remain. False when it is not theirs.
 */
export const deleteConversation = async (
  db: Database,
  userId: string,
  id: string,
): Promise<boolean> => {
  if (!isConversationId(id)) {
    return false;
  }

  return db.transaction(async (tx) => {
    const deleted = await tx
      .delete(conversations)
      .where(and(eq(conversations.id, id), eq(conversations.userId, userId)))
      .returning({ id: conversations.id });
    if (deleted.length === 0) {
      return false;
    }

    await recomputeConceptMemories(tx, userId);
    return true;
  });
};

interface RunRecord {
  /** The stage in the state the run saved. */
  stage: Stage;
  /** The student's newest message in the run, if it had one. */
  userText: string | null;
}

/**
 * A run ended on the conversation: it is active now, at the saved stage,
 * and the first message names it until research does.
 */
export const recordConversationRun = async (
  db: Database,
  id: string,
  { stage, userText }: RunRecord,
  now = new Date(),
): Promise<void> => {
  const autoTitle = userText ? createAutoTitle(userText) : null;
  await db
    .update(conversations)
    .set({
      stage,
      status: getStoredStatus(stage),
      lastActivityAt: now,
      title: sql`coalesce(${conversations.title}, ${autoTitle})`,
    })
    .where(eq(conversations.id, id));
};
