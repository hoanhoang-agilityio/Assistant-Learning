import type { LearningHistory, TopicHistory } from "@repo/shared/schemas";
import { and, asc, eq, isNotNull } from "drizzle-orm";

import type { Database } from "../client";
import { conversations, quizAttempts } from "../schema";

/** ISO timestamps in UTC, so they sort as text. */
const lastGradedAt = ({ attempts }: TopicHistory): string =>
  attempts.at(-1)?.submittedAt ?? "";

/**
 * The student's graded attempts, grouped by conversation (one topic each):
 * scores oldest first and the latest attempt's concept mastery. Topics the
 * student forgot in the Memory panel still show: this is the record of
 * what was graded, not what the agent remembers. Attempts never graded are
 * left out.
 */
export const getLearningHistory = async (
  db: Database,
  userId: string,
): Promise<LearningHistory> => {
  const rows = await db
    .select({
      conversationId: quizAttempts.conversationId,
      title: conversations.title,
      topic: conversations.topic,
      attemptNo: quizAttempts.attemptNo,
      scorePct: quizAttempts.scorePct,
      tier: quizAttempts.tier,
      mastery: quizAttempts.mastery,
      submittedAt: quizAttempts.submittedAt,
    })
    .from(quizAttempts)
    .innerJoin(conversations, eq(conversations.id, quizAttempts.conversationId))
    .where(
      and(
        eq(conversations.userId, userId),
        eq(quizAttempts.status, "submitted"),
        isNotNull(quizAttempts.scorePct),
        isNotNull(quizAttempts.tier),
        isNotNull(quizAttempts.submittedAt),
      ),
    )
    .orderBy(asc(quizAttempts.submittedAt), asc(quizAttempts.attemptNo));

  const topics = new Map<string, TopicHistory>();
  for (const row of rows) {
    if (row.scorePct === null || row.tier === null || !row.submittedAt) {
      continue;
    }
    const attempt = {
      attemptNo: row.attemptNo,
      score: { percent: row.scorePct, tier: row.tier },
      submittedAt: row.submittedAt.toISOString(),
    };
    const topic = topics.get(row.conversationId);
    if (topic) {
      topic.attempts.push(attempt);
      topic.mastery = row.mastery ?? [];
    } else {
      topics.set(row.conversationId, {
        conversationId: row.conversationId,
        title: row.title ?? row.topic,
        attempts: [attempt],
        mastery: row.mastery ?? [],
      });
    }
  }

  return {
    topics: Array.from(topics.values()).sort((a, b) =>
      lastGradedAt(b).localeCompare(lastGradedAt(a)),
    ),
  };
};
