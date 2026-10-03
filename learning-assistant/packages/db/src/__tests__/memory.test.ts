import { EMPTY_STUDENT_MEMORY } from "@repo/shared/constants/memory";
import type { Quiz } from "@repo/shared/schemas";
import { beforeEach, describe, expect, it } from "vitest";

import type { Database } from "../client";
import {
  createConversation,
  deleteConversation,
} from "../repositories/conversations";
import {
  deleteConceptMemory,
  deleteTopicMemory,
  getStudentMemory,
  saveLearnerProfile,
} from "../repositories/memory";
import {
  recordEvaluation,
  recordQuiz,
  recordResearch,
} from "../repositories/records";
import { deleteUser, ensureUser } from "../repositories/users";
import { createTestDatabase } from "../testing";

const RESEARCH = {
  title: "JavaScript closures",
  summary: "Functions remember their scope.",
  keyInsight: "Scope travels with the function.",
  keyTerms: [],
  sources: [],
};

const QUIZ: Quiz = {
  id: "quiz_1",
  questions: [
    { id: "q1", concept: "Scope", question: "Q1?", options: ["a", "b"] },
    { id: "q2", concept: "scope", question: "Q2?", options: ["a", "b"] },
    { id: "q3", concept: "Closures", question: "Q3?", options: ["a", "b"] },
  ],
  answers: {},
  answerKeySealed: "sealed-key",
  submitted: false,
};

/** Scope 1 of 2, Closures 1 of 1: 67%. */
const GRADED = {
  quiz: { ...QUIZ, answers: { q1: 0, q2: 1, q3: 0 }, submitted: true },
  evaluation: {
    correct: 2,
    total: 3,
    percent: 67,
    weakestConcept: "Scope",
    perQuestion: [],
    mastery: [
      { concept: "Scope", percent: 50 },
      { concept: "Closures", percent: 100 },
    ],
  },
  score: { percent: 66.7, tier: "Practitioner" as const },
  feedback: { a2uiOperations: [], summary: "Review scope." },
};

const PERFECT = {
  ...GRADED,
  evaluation: {
    ...GRADED.evaluation,
    mastery: [
      { concept: "Scope", percent: 100 },
      { concept: "Closures", percent: 100 },
    ],
  },
  score: { percent: 100, tier: "Master" as const },
};

describe("memory repository", () => {
  let db: Database;
  let alice: string;
  let bob: string;

  /** A conversation of Alice's on closures, graded with `graded`. */
  const studyClosures = async (
    graded: Parameters<typeof recordEvaluation>[2] = GRADED,
  ) => {
    const { id } = await createConversation(db, alice);
    await recordResearch(db, id, { topic: "closures", research: RESEARCH });
    await recordQuiz(db, id, QUIZ);
    await recordEvaluation(db, id, graded);
    return id;
  };

  const conceptsOf = async (userId: string) =>
    (await getStudentMemory(db, userId)).concepts.map(
      ({ key, correct, total, percent }) => ({ key, correct, total, percent }),
    );

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

  it("is empty for a new student", async () => {
    expect(await getStudentMemory(db, alice)).toEqual(EMPTY_STUDENT_MEMORY);
  });

  describe("profile", () => {
    it("changes only the fields given, and forgets one set to null", async () => {
      await saveLearnerProfile(
        db,
        alice,
        { level: "advanced", language: "Vietnamese" },
        "agent",
      );
      await saveLearnerProfile(
        db,
        alice,
        { style: "short analogies" },
        "agent",
      );
      expect((await getStudentMemory(db, alice)).profile).toEqual({
        level: "advanced",
        style: "short analogies",
        language: "Vietnamese",
      });

      await saveLearnerProfile(db, alice, { language: null }, "agent");
      expect((await getStudentMemory(db, alice)).profile.language).toBeNull();
    });

    it("keeps what the student set from what a run learns later", async () => {
      await saveLearnerProfile(
        db,
        alice,
        { language: "Vietnamese", style: "analogies" },
        "agent",
      );
      await saveLearnerProfile(db, alice, { language: "English" }, "student");

      const kept = await saveLearnerProfile(
        db,
        alice,
        { language: "French", style: "short answers", level: "beginner" },
        "agent",
      );

      expect(kept).toEqual({
        level: "beginner",
        style: "short answers",
        language: "English",
      });
    });

    it("lets a run learn a field again once the student forgets it", async () => {
      await saveLearnerProfile(db, alice, { language: "English" }, "student");
      await saveLearnerProfile(db, alice, { language: null }, "student");

      await saveLearnerProfile(db, alice, { language: "French" }, "agent");
      expect((await getStudentMemory(db, alice)).profile.language).toBe(
        "French",
      );
    });

    it("lets the student change their own setting", async () => {
      await saveLearnerProfile(db, alice, { level: "advanced" }, "student");
      await saveLearnerProfile(db, alice, { level: "beginner" }, "student");

      expect((await getStudentMemory(db, alice)).profile.level).toBe(
        "beginner",
      );
    });

    it("is one student's only", async () => {
      await saveLearnerProfile(db, alice, { level: "advanced" }, "student");
      expect(await getStudentMemory(db, bob)).toEqual(EMPTY_STUDENT_MEMORY);
    });
  });

  describe("concepts and topics", () => {
    it("takes in each graded attempt, by concept and by topic", async () => {
      const id = await studyClosures();

      expect(await conceptsOf(alice)).toEqual([
        { key: "scope", correct: 1, total: 2, percent: 50 },
        { key: "closures", correct: 1, total: 1, percent: 100 },
      ]);
      expect((await getStudentMemory(db, alice)).topics).toMatchObject([
        {
          conversationId: id,
          topic: "closures",
          bestPercent: 67,
          latestPercent: 67,
          attempts: 1,
        },
      ]);
      expect(await getStudentMemory(db, bob)).toEqual(EMPTY_STUDENT_MEMORY);
    });

    it("adds up retakes and keeps the best score", async () => {
      const id = await studyClosures();
      await recordEvaluation(db, id, PERFECT);
      await recordEvaluation(db, id, GRADED);

      expect(await conceptsOf(alice)).toEqual([
        { key: "scope", correct: 4, total: 6, percent: 67 },
        { key: "closures", correct: 3, total: 3, percent: 100 },
      ]);
      expect((await getStudentMemory(db, alice)).topics).toMatchObject([
        { bestPercent: 100, latestPercent: 67, attempts: 3 },
      ]);
    });

    it("rebuilds concepts from the attempts that remain when a conversation is deleted", async () => {
      const first = await studyClosures();
      const second = await studyClosures(PERFECT);
      expect(await conceptsOf(alice)).toEqual([
        { key: "scope", correct: 3, total: 4, percent: 75 },
        { key: "closures", correct: 2, total: 2, percent: 100 },
      ]);

      expect(await deleteConversation(db, alice, first)).toBe(true);
      expect(await conceptsOf(alice)).toEqual([
        { key: "scope", correct: 2, total: 2, percent: 100 },
        { key: "closures", correct: 1, total: 1, percent: 100 },
      ]);
      const { topics } = await getStudentMemory(db, alice);
      expect(topics.map(({ conversationId }) => conversationId)).toEqual([
        second,
      ]);

      await deleteConversation(db, alice, second);
      expect(await conceptsOf(alice)).toEqual([]);
    });

    it("keeps a deleted concept deleted when a conversation is deleted", async () => {
      const first = await studyClosures();
      await studyClosures();
      expect(await deleteConceptMemory(db, alice, "scope")).toBe(true);

      await deleteConversation(db, alice, first);
      expect((await conceptsOf(alice)).map(({ key }) => key)).toEqual([
        "closures",
      ]);
    });

    it("forgets a topic but keeps its conversation", async () => {
      const id = await studyClosures();

      expect(await deleteTopicMemory(db, bob, id)).toBe(false);
      expect(await deleteTopicMemory(db, alice, "not-a-uuid")).toBe(false);
      expect(await deleteTopicMemory(db, alice, id)).toBe(true);
      expect((await getStudentMemory(db, alice)).topics).toEqual([]);
    });

    it("deletes nothing of another student's", async () => {
      await studyClosures();

      expect(await deleteConceptMemory(db, bob, "scope")).toBe(false);
      expect(await conceptsOf(alice)).toHaveLength(2);
    });
  });

  it("goes with the user", async () => {
    await studyClosures();
    await saveLearnerProfile(db, alice, { level: "advanced" }, "student");

    await deleteUser(db, "user_alice");
    expect(await getStudentMemory(db, alice)).toEqual(EMPTY_STUDENT_MEMORY);
  });
});
