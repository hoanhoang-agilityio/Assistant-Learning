import { EMPTY_PROFILE } from "@repo/shared/constants/memory";
import type {
  ConceptMemory,
  Evaluation,
  LearnerProfile,
  ProfileField,
  ProfileUpdate,
  QuizQuestion,
  StudentMemory,
  TopicMemory,
} from "@repo/shared/schemas";
import {
  calculateConceptPercent,
  countConceptResults,
} from "@repo/shared/utils/memory";
import { and, desc, eq, sql } from "drizzle-orm";
import { z } from "zod";

import type { Database, Transaction } from "../client";
import {
  conceptMemories,
  conversations,
  learnerProfiles,
  quizAttempts,
  topicMemories,
} from "../schema";

interface GradedAttempt {
  questions: readonly Pick<QuizQuestion, "concept">[];
  mastery: Evaluation["mastery"];
  /** The attempt's whole score percent. */
  percent: number;
}

const toConceptMemory = (
  row: typeof conceptMemories.$inferSelect,
): ConceptMemory => ({
  key: row.key,
  concept: row.concept,
  correct: row.correct,
  total: row.total,
  percent: calculateConceptPercent(row.correct, row.total),
  updatedAt: row.updatedAt.toISOString(),
});

const toTopicMemory = (
  row: typeof topicMemories.$inferSelect,
): TopicMemory => ({
  conversationId: row.conversationId,
  topic: row.topic,
  bestPercent: row.bestPct,
  latestPercent: row.latestPct,
  attempts: row.attempts,
  updatedAt: row.updatedAt.toISOString(),
});

/** The profile's own fields, without who set them. */
const PROFILE_COLUMNS = {
  level: learnerProfiles.level,
  style: learnerProfiles.style,
  language: learnerProfiles.language,
};

/** Weakest first; among equals, the one with more evidence. */
const byMastery = (a: ConceptMemory, b: ConceptMemory): number =>
  a.percent - b.percent || b.total - a.total;

/** Everything kept about the student: profile, concepts weakest first, topics newest first. */
export const getStudentMemory = async (
  db: Database,
  userId: string,
): Promise<StudentMemory> => {
  const [profile] = await db
    .select(PROFILE_COLUMNS)
    .from(learnerProfiles)
    .where(eq(learnerProfiles.userId, userId));
  const concepts = await db
    .select()
    .from(conceptMemories)
    .where(eq(conceptMemories.userId, userId));
  const topics = await db
    .select()
    .from(topicMemories)
    .where(eq(topicMemories.userId, userId))
    .orderBy(desc(topicMemories.updatedAt));

  return {
    profile: profile ?? EMPTY_PROFILE,
    concepts: concepts.map(toConceptMemory).sort(byMastery),
    topics: topics.map(toTopicMemory),
  };
};

/** Who changes the profile: the student, or what a run noticed about them. */
export type ProfileSource = "student" | "agent";

/**
 * Changes the fields `update` names and keeps the rest; `null` forgets a
 * field. A field the student sets is theirs: what a run learns later never
 * changes it, until the student forgets it. Returns the profile as kept.
 */
export const saveLearnerProfile = async (
  db: Database,
  userId: string,
  update: ProfileUpdate,
  source: ProfileSource,
  now = new Date(),
): Promise<LearnerProfile> =>
  db.transaction(async (tx) => {
    const [current] = await tx
      .select({ studentFields: learnerProfiles.studentFields })
      .from(learnerProfiles)
      .where(eq(learnerProfiles.userId, userId));
    const studentFields = new Set(current?.studentFields ?? []);
    const changes = Object.fromEntries(
      (Object.entries(update) as [ProfileField, string | null | undefined][])
        .filter(([, value]) => value !== undefined)
        .filter(([field]) => source === "student" || !studentFields.has(field)),
    ) as ProfileUpdate;

    if (source === "student") {
      for (const [field, value] of Object.entries(changes)) {
        if (value === null) {
          studentFields.delete(field as ProfileField);
        } else {
          studentFields.add(field as ProfileField);
        }
      }
    }
    const kept = { ...changes, studentFields: [...studentFields] };

    const [row] = await tx
      .insert(learnerProfiles)
      .values({ ...EMPTY_PROFILE, ...kept, userId, updatedAt: now })
      .onConflictDoUpdate({
        target: learnerProfiles.userId,
        set: { ...kept, updatedAt: now },
      })
      .returning(PROFILE_COLUMNS);
    return row ?? EMPTY_PROFILE;
  });

/** Forgets one concept until a new graded attempt tests it. False when there was none. */
export const deleteConceptMemory = async (
  db: Database,
  userId: string,
  key: string,
): Promise<boolean> => {
  const deleted = await db
    .delete(conceptMemories)
    .where(
      and(eq(conceptMemories.userId, userId), eq(conceptMemories.key, key)),
    )
    .returning({ key: conceptMemories.key });
  return deleted.length > 0;
};

/** Forgets one topic; its conversation stays. False when it is not theirs. */
export const deleteTopicMemory = async (
  db: Database,
  userId: string,
  conversationId: string,
): Promise<boolean> => {
  if (!z.uuid().safeParse(conversationId).success) {
    return false;
  }

  const deleted = await db
    .delete(topicMemories)
    .where(
      and(
        eq(topicMemories.userId, userId),
        eq(topicMemories.conversationId, conversationId),
      ),
    )
    .returning({ id: topicMemories.conversationId });
  return deleted.length > 0;
};

/**
 * A graded attempt adds to the student's mastery of each concept it tested,
 * and to its conversation's topic: best and latest score, attempt count.
 * Runs inside the transaction that grades the attempt.
 */
export const rememberGradedAttempt = async (
  tx: Transaction,
  conversationId: string,
  { questions, mastery, percent }: GradedAttempt,
  now: Date,
): Promise<void> => {
  const [conversation] = await tx
    .select({
      userId: conversations.userId,
      topic: sql<
        string | null
      >`coalesce(${conversations.topic}, ${conversations.title})`,
    })
    .from(conversations)
    .where(eq(conversations.id, conversationId));
  if (!conversation) {
    return;
  }

  const { userId, topic } = conversation;
  const results = countConceptResults(questions, mastery);
  if (results.length > 0) {
    await tx
      .insert(conceptMemories)
      .values(results.map((result) => ({ ...result, userId, updatedAt: now })))
      .onConflictDoUpdate({
        target: [conceptMemories.userId, conceptMemories.key],
        set: {
          concept: sql`excluded.concept`,
          correct: sql`${conceptMemories.correct} + excluded.correct`,
          total: sql`${conceptMemories.total} + excluded.total`,
          updatedAt: now,
        },
      });
  }

  if (topic) {
    await tx
      .insert(topicMemories)
      .values({
        conversationId,
        userId,
        topic,
        bestPct: percent,
        latestPct: percent,
        attempts: 1,
        updatedAt: now,
      })
      .onConflictDoUpdate({
        target: topicMemories.conversationId,
        set: {
          topic,
          bestPct: sql`greatest(${topicMemories.bestPct}, ${percent})`,
          latestPct: percent,
          attempts: sql`${topicMemories.attempts} + 1`,
          updatedAt: now,
        },
      });
  }
};

/**
 * Rebuilds each concept the student still has from the graded attempts
 * that remain, after a conversation was deleted; a concept no attempt
 * tests any more is forgotten. A concept the student deleted stays deleted.
 * Topics need nothing: theirs went with the conversation.
 */
export const recomputeConceptMemories = async (
  tx: Transaction,
  userId: string,
): Promise<void> => {
  const attempts = await tx
    .select({
      questions: quizAttempts.questions,
      mastery: quizAttempts.mastery,
    })
    .from(quizAttempts)
    .innerJoin(conversations, eq(conversations.id, quizAttempts.conversationId))
    .where(
      and(
        eq(conversations.userId, userId),
        eq(quizAttempts.status, "submitted"),
      ),
    );
  const totals = new Map<string, { correct: number; total: number }>();
  for (const { questions, mastery } of attempts) {
    for (const { key, correct, total } of countConceptResults(
      questions,
      mastery ?? [],
    )) {
      const sum = totals.get(key) ?? { correct: 0, total: 0 };
      totals.set(key, {
        correct: sum.correct + correct,
        total: sum.total + total,
      });
    }
  }

  const kept = await tx
    .select({ key: conceptMemories.key })
    .from(conceptMemories)
    .where(eq(conceptMemories.userId, userId));
  for (const { key } of kept) {
    const where = and(
      eq(conceptMemories.userId, userId),
      eq(conceptMemories.key, key),
    );
    const sum = totals.get(key);
    if (sum) {
      await tx.update(conceptMemories).set(sum).where(where);
    } else {
      await tx.delete(conceptMemories).where(where);
    }
  }
};
