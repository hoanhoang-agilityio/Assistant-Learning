import type {
  DraftAnswers,
  Evaluation,
  Feedback,
  Material,
  Quiz,
  QuizAttemptSummary,
  ResearchResult,
  Score,
  Stage,
} from "@repo/shared/schemas";
import { getStoredStatus } from "@repo/shared/utils/conversations";
import { and, desc, eq, max, sql } from "drizzle-orm";

import type { Database, Transaction } from "../client";
import { conversations, material, quizAttempts, research } from "../schema";
import { rememberGradedAttempt } from "./memory";

interface ResearchRecord {
  topic: string;
  research: ResearchResult;
}

interface EvaluationRecord {
  /** The graded quiz with the answers that were graded. */
  quiz: Quiz;
  evaluation: Evaluation;
  score: Score;
  feedback: Feedback;
}

/** The conversation moved to `stage`; it is active (or completed) and touched now. */
const moveConversation = (
  db: Database | Transaction,
  id: string,
  stage: Stage,
  now: Date,
) =>
  db
    .update(conversations)
    .set({ stage, status: getStoredStatus(stage), lastActivityAt: now })
    .where(eq(conversations.id, id));

const nextAttemptNo = async (
  tx: Transaction,
  conversationId: string,
): Promise<number> => {
  const [row] = await tx
    .select({ last: max(quizAttempts.attemptNo) })
    .from(quizAttempts)
    .where(eq(quizAttempts.conversationId, conversationId));
  return (row?.last ?? 0) + 1;
};

/**
 * Research finished: it is saved, the topic set, and the research title
 * names the conversation unless the student renamed it.
 */
export const recordResearch = async (
  db: Database,
  conversationId: string,
  { topic, research: result }: ResearchRecord,
  now = new Date(),
): Promise<void> => {
  await db.transaction(async (tx) => {
    await tx
      .insert(research)
      .values({
        conversationId,
        payload: result,
        sources: result.sources,
        updatedAt: now,
      })
      .onConflictDoUpdate({
        target: research.conversationId,
        set: { payload: result, sources: result.sources, updatedAt: now },
      });
    await tx
      .update(conversations)
      .set({
        topic,
        stage: "research",
        status: "active",
        lastActivityAt: now,
        title: sql`case when ${conversations.isTitleCustom} then ${conversations.title} else ${result.title} end`,
      })
      .where(eq(conversations.id, conversationId));
  });
};

/** The Material or Simplify agent finished: the learning material as it wrote it. */
export const recordMaterial = async (
  db: Database,
  conversationId: string,
  { original, simplified }: Material,
  now = new Date(),
): Promise<void> => {
  await db.transaction(async (tx) => {
    await tx
      .insert(material)
      .values({ conversationId, original, simplified, updatedAt: now })
      .onConflictDoUpdate({
        target: material.conversationId,
        set: { original, simplified, updatedAt: now },
      });
    await moveConversation(tx, conversationId, "material", now);
  });
};

/** A new quiz starts an attempt, its answer key still sealed. */
export const recordQuiz = async (
  db: Database,
  conversationId: string,
  quiz: Quiz,
  now = new Date(),
): Promise<void> => {
  await db.transaction(async (tx) => {
    await tx.insert(quizAttempts).values({
      conversationId,
      quizId: quiz.id,
      attemptNo: await nextAttemptNo(tx, conversationId),
      questions: quiz.questions,
      answerKey: quiz.answerKeySealed,
      answers: quiz.answers,
      status: "in_progress",
      startedAt: now,
    });
    await moveConversation(tx, conversationId, "quiz", now);
  });
};

/**
 * The quiz was graded. It closes the attempt the quiz started; a retake of
 * a quiz already graded is a new attempt. The student's concept mastery
 * and topic scores take the result in (E3).
 */
export const recordEvaluation = async (
  db: Database,
  conversationId: string,
  { quiz, evaluation, score, feedback }: EvaluationRecord,
  now = new Date(),
): Promise<void> => {
  const graded = {
    answers: quiz.answers,
    status: "submitted" as const,
    scorePct: Math.round(score.percent),
    tier: score.tier,
    mastery: evaluation.mastery,
    feedback,
    submittedAt: now,
  };

  await db.transaction(async (tx) => {
    const [open] = await tx
      .select({ id: quizAttempts.id })
      .from(quizAttempts)
      .where(
        and(
          eq(quizAttempts.conversationId, conversationId),
          eq(quizAttempts.quizId, quiz.id),
          eq(quizAttempts.status, "in_progress"),
        ),
      )
      .orderBy(desc(quizAttempts.attemptNo))
      .limit(1);
    if (open) {
      await tx
        .update(quizAttempts)
        .set(graded)
        .where(eq(quizAttempts.id, open.id));
    } else {
      await tx.insert(quizAttempts).values({
        conversationId,
        quizId: quiz.id,
        attemptNo: await nextAttemptNo(tx, conversationId),
        questions: quiz.questions,
        answerKey: quiz.answerKeySealed,
        startedAt: now,
        ...graded,
      });
    }
    await rememberGradedAttempt(
      tx,
      conversationId,
      {
        questions: quiz.questions,
        mastery: evaluation.mastery,
        percent: graded.scorePct,
      },
      now,
    );
    await moveConversation(tx, conversationId, "evaluation", now);
  });
};

/** The conversation's quiz attempts, oldest first, without answer keys. */
export const listQuizAttempts = async (
  db: Database,
  conversationId: string,
): Promise<QuizAttemptSummary[]> => {
  const rows = await db
    .select({
      id: quizAttempts.id,
      attemptNo: quizAttempts.attemptNo,
      status: quizAttempts.status,
      questions: quizAttempts.questions,
      answers: quizAttempts.answers,
      scorePct: quizAttempts.scorePct,
      tier: quizAttempts.tier,
      startedAt: quizAttempts.startedAt,
      submittedAt: quizAttempts.submittedAt,
    })
    .from(quizAttempts)
    .where(eq(quizAttempts.conversationId, conversationId))
    .orderBy(quizAttempts.attemptNo);
  return rows.map((row) => ({
    id: row.id,
    attemptNo: row.attemptNo,
    status: row.status,
    questionCount: row.questions.length,
    answeredCount: Object.keys(row.answers).length,
    score:
      row.scorePct !== null && row.tier !== null
        ? { percent: row.scorePct, tier: row.tier }
        : null,
    startedAt: row.startedAt.toISOString(),
    submittedAt: row.submittedAt?.toISOString() ?? null,
  }));
};

/** Only answers for the attempt's own questions, with an option that exists. */
const keepValidAnswers = (
  questions: readonly Quiz["questions"][number][],
  answers: DraftAnswers["answers"],
): DraftAnswers["answers"] =>
  Object.fromEntries(
    questions.flatMap(({ id, options }) => {
      const answer = answers[id];
      return answer !== undefined && answer < options.length
        ? [[id, answer]]
        : [];
    }),
  );

/**
 * Keeps the answers picked so far for `draft.quizId`, without a run. They go
 * to that quiz's open attempt; when its latest attempt was graded, the
 * student is retaking it, so a new attempt opens with the same questions
 * (grading closes it, as it closes any open attempt). False when the
 * conversation has no such quiz.
 */
export const saveDraftAnswers = async (
  db: Database,
  conversationId: string,
  draft: DraftAnswers,
  now = new Date(),
): Promise<boolean> =>
  db.transaction(async (tx) => {
    const [latest] = await tx
      .select()
      .from(quizAttempts)
      .where(
        and(
          eq(quizAttempts.conversationId, conversationId),
          eq(quizAttempts.quizId, draft.quizId),
        ),
      )
      .orderBy(desc(quizAttempts.attemptNo))
      .limit(1);
    if (!latest) {
      return false;
    }

    const answers = keepValidAnswers(latest.questions, draft.answers);
    if (latest.status === "in_progress") {
      await tx
        .update(quizAttempts)
        .set({ answers })
        .where(eq(quizAttempts.id, latest.id));
    } else {
      await tx.insert(quizAttempts).values({
        conversationId,
        quizId: latest.quizId,
        attemptNo: await nextAttemptNo(tx, conversationId),
        questions: latest.questions,
        answerKey: latest.answerKey,
        answers,
        status: "in_progress",
        startedAt: now,
      });
    }
    return true;
  });

/**
 * The answers picked so far in the conversation's latest attempt, or `null`
 * when it has none or the latest attempt is graded.
 */
export const getDraftAnswers = async (
  db: Database,
  conversationId: string,
): Promise<DraftAnswers | null> => {
  const [latest] = await db
    .select({
      quizId: quizAttempts.quizId,
      answers: quizAttempts.answers,
      status: quizAttempts.status,
    })
    .from(quizAttempts)
    .where(eq(quizAttempts.conversationId, conversationId))
    .orderBy(desc(quizAttempts.attemptNo))
    .limit(1);
  return latest?.status === "in_progress"
    ? { quizId: latest.quizId, answers: latest.answers }
    : null;
};
