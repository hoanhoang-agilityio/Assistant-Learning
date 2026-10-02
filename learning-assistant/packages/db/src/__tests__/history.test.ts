import type { Quiz } from "@repo/shared/schemas";
import { beforeEach, describe, expect, it } from "vitest";

import type { Database } from "../client";
import {
  createConversation,
  deleteConversation,
  renameConversation,
} from "../repositories/conversations";
import { getLearningHistory } from "../repositories/history";
import { deleteTopicMemory } from "../repositories/memory";
import {
  recordEvaluation,
  recordQuiz,
  recordResearch,
} from "../repositories/records";
import { ensureUser } from "../repositories/users";
import { createTestDatabase } from "../testing";

const research = (title: string) => ({
  title,
  summary: "Summary.",
  keyInsight: "Insight.",
  keyTerms: [],
  sources: [],
});

const QUIZ: Quiz = {
  id: "quiz_1",
  questions: [
    { id: "q1", concept: "Scope", question: "Q1?", options: ["a", "b"] },
    { id: "q2", concept: "Closures", question: "Q2?", options: ["a", "b"] },
  ],
  answers: {},
  answerKeySealed: "sealed-key",
  submitted: false,
};

const graded = (percent: number, scopePercent: number) => ({
  quiz: { ...QUIZ, answers: { q1: 0, q2: 1 }, submitted: true },
  evaluation: {
    correct: 1,
    total: 2,
    percent,
    weakestConcept: "Scope",
    perQuestion: [],
    mastery: [
      { concept: "Scope", percent: scopePercent },
      { concept: "Closures", percent: 100 },
    ],
  },
  score: { percent, tier: "Practitioner" as const },
  feedback: { a2uiOperations: [], summary: "Ok." },
});

const at = (day: number) => new Date(Date.UTC(2026, 9, day, 10));

describe("learning history", () => {
  let db: Database;
  let alice: string;
  let bob: string;

  /** A conversation of `userId`'s on `topic`, with one attempt per score, one day apart from `day`. */
  const study = async (
    userId: string,
    topic: string,
    scores: number[],
    day: number,
  ) => {
    const { id } = await createConversation(db, userId);
    await recordResearch(db, id, { topic, research: research(topic) });
    for (const [index, percent] of scores.entries()) {
      await recordQuiz(db, id, QUIZ);
      await recordEvaluation(db, id, graded(percent, percent), at(day + index));
    }
    return id;
  };

  beforeEach(async () => {
    db = await createTestDatabase();
    alice = await ensureUser(db, {
      clerkUserId: "user_alice",
      getEmail: async () => null,
    });
    bob = await ensureUser(db, {
      clerkUserId: "user_bob",
      getEmail: async () => null,
    });
  });

  it("is empty for a student with no graded quiz", async () => {
    const { id } = await createConversation(db, alice);
    await recordQuiz(db, id, QUIZ);

    expect(await getLearningHistory(db, alice)).toEqual({ topics: [] });
  });

  it("lists each topic's scores oldest first and its latest mastery", async () => {
    const id = await study(alice, "Closures", [40, 75], 1);

    expect(await getLearningHistory(db, alice)).toEqual({
      topics: [
        {
          conversationId: id,
          title: "Closures",
          attempts: [
            {
              attemptNo: 1,
              score: { percent: 40, tier: "Practitioner" },
              submittedAt: at(1).toISOString(),
            },
            {
              attemptNo: 2,
              score: { percent: 75, tier: "Practitioner" },
              submittedAt: at(2).toISOString(),
            },
          ],
          mastery: [
            { concept: "Scope", percent: 75 },
            { concept: "Closures", percent: 100 },
          ],
        },
      ],
    });
  });

  it("puts the topic graded last first, and shows the student's own title", async () => {
    const closures = await study(alice, "Closures", [40, 75], 1);
    const promises = await study(alice, "Promises", [90], 3);
    await renameConversation(db, alice, closures, "My closures");

    const later = await study(alice, "Closures again", [60], 10);
    const topics = (await getLearningHistory(db, alice)).topics;

    expect(topics.map(({ conversationId }) => conversationId)).toEqual([
      later,
      promises,
      closures,
    ]);
    expect(topics.at(-1)?.title).toBe("My closures");
  });

  it("shows only the student's own topics", async () => {
    await study(alice, "Closures", [40], 1);
    const bobs = await study(bob, "Recursion", [80], 2);

    expect(
      (await getLearningHistory(db, bob)).topics.map(
        ({ conversationId }) => conversationId,
      ),
    ).toEqual([bobs]);
  });

  it("keeps a topic forgotten in memory, and drops a deleted conversation", async () => {
    const closures = await study(alice, "Closures", [40], 1);
    const promises = await study(alice, "Promises", [90], 2);

    await deleteTopicMemory(db, alice, closures);
    await deleteConversation(db, alice, promises);

    expect(
      (await getLearningHistory(db, alice)).topics.map(
        ({ conversationId }) => conversationId,
      ),
    ).toEqual([closures]);
  });
});
