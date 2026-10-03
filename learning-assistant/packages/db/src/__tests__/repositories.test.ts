import type { Quiz } from "@repo/shared/schemas";
import { beforeEach, describe, expect, it } from "vitest";

import type { Database } from "../client";
import {
  createConversation,
  deleteConversation,
  filterOwnedConversationIds,
  findConversationOwner,
  getConversation,
  listConversations,
  recordConversationRun,
  renameConversation,
} from "../repositories/conversations";
import {
  getDraftAnswers,
  listQuizAttempts,
  recordEvaluation,
  recordMaterial,
  recordQuiz,
  recordResearch,
  saveDraftAnswers,
} from "../repositories/records";
import { getUserSettings, saveUserSettings } from "../repositories/settings";
import {
  deleteUser,
  ensureUser,
  listUserConversationIds,
} from "../repositories/users";
import { quizAttempts } from "../schema";
import { createTestDatabase } from "../testing";

const RESEARCH = {
  title: "JavaScript closures",
  summary: "Functions remember their scope.",
  keyInsight: "Scope travels with the function.",
  keyTerms: [],
  sources: [{ title: "MDN", url: "https://developer.mozilla.org" }],
};

const QUIZ: Quiz = {
  id: "quiz_1",
  questions: [
    { id: "q1", concept: "Scope", question: "Q1?", options: ["a", "b"] },
    { id: "q2", concept: "Scope", question: "Q2?", options: ["a", "b"] },
  ],
  answers: {},
  answerKeySealed: "sealed-key",
  submitted: false,
};

const GRADED = {
  quiz: { ...QUIZ, answers: { q1: 0, q2: 1 }, submitted: true },
  evaluation: {
    correct: 1,
    total: 2,
    percent: 50,
    weakestConcept: "Scope",
    perQuestion: [],
    mastery: [{ concept: "Scope", percent: 50 }],
  },
  score: { percent: 50, tier: "Practitioner" as const },
  feedback: { a2uiOperations: [], summary: "Review scope." },
};

const noEmail = async () => null;

describe("repositories", () => {
  let db: Database;
  let alice: string;
  let bob: string;

  beforeEach(async () => {
    db = await createTestDatabase();
    alice = await ensureUser(db, {
      clerkUserId: "user_alice",
      getEmail: async () => "alice@example.com",
    });
    bob = await ensureUser(db, { clerkUserId: "user_bob", getEmail: noEmail });
  });

  describe("users", () => {
    it("creates a user once and asks for the email only then", async () => {
      let asked = 0;
      const getEmail = async () => {
        asked += 1;
        return null;
      };
      const first = await ensureUser(db, { clerkUserId: "user_c", getEmail });
      const again = await ensureUser(db, { clerkUserId: "user_c", getEmail });
      expect(again).toBe(first);
      expect(asked).toBe(1);
    });

    it("deletes a user with their conversations", async () => {
      const { id } = await createConversation(db, alice);
      expect(await listUserConversationIds(db, "user_alice")).toEqual([id]);

      expect(await deleteUser(db, "user_alice")).toBe(true);
      expect(await findConversationOwner(db, id)).toBeUndefined();
      expect(await deleteUser(db, "user_alice")).toBe(false);
    });
  });

  describe("conversations", () => {
    it("reuses the one conversation that has not started", async () => {
      const first = await createConversation(db, alice);
      const again = await createConversation(db, alice);
      expect(again.id).toBe(first.id);

      await recordConversationRun(db, first.id, {
        stage: "idle",
        userText: "Teach me closures",
      });
      const next = await createConversation(db, alice);
      expect(next.id).not.toBe(first.id);
      expect(await listConversations(db, alice)).toHaveLength(2);
    });

    it("keeps each user's conversations to them", async () => {
      const { id } = await createConversation(db, alice);

      expect(await findConversationOwner(db, id)).toBe("user_alice");
      expect(await getConversation(db, bob, id)).toBeNull();
      expect(await renameConversation(db, bob, id, "Mine")).toBeNull();
      expect(await deleteConversation(db, bob, id)).toBe(false);
      expect(await listConversations(db, bob)).toEqual([]);
      expect(
        await filterOwnedConversationIds(db, "user_bob", [id, "not-a-uuid"]),
      ).toEqual(new Set());
      expect(await filterOwnedConversationIds(db, "user_alice", [id])).toEqual(
        new Set([id]),
      );
    });

    it("finds no owner for a thread id that is not a uuid", async () => {
      expect(await findConversationOwner(db, "thread-1")).toBeUndefined();
      expect(await getConversation(db, alice, "thread-1")).toBeNull();
    });

    it("titles a conversation from its first message, then from research", async () => {
      const { id } = await createConversation(db, alice);
      await recordConversationRun(db, id, {
        stage: "idle",
        userText: "Teach me\nclosures",
      });
      await recordConversationRun(db, id, {
        stage: "idle",
        userText: "Something else",
      });
      expect((await getConversation(db, alice, id))?.title).toBe(
        "Teach me closures",
      );

      await recordResearch(db, id, { topic: "closures", research: RESEARCH });
      expect(await getConversation(db, alice, id)).toMatchObject({
        title: RESEARCH.title,
        topic: "closures",
        stage: "research",
      });
    });

    it("keeps a name the student gave over the research title", async () => {
      const { id } = await createConversation(db, alice);
      await renameConversation(db, alice, id, "My closures notes");
      await recordResearch(db, id, { topic: "closures", research: RESEARCH });
      expect((await getConversation(db, alice, id))?.title).toBe(
        "My closures notes",
      );
    });

    it("reads a week-old active conversation as abandoned", async () => {
      const { id } = await createConversation(db, alice);
      await recordConversationRun(
        db,
        id,
        { stage: "quiz", userText: null },
        new Date("2026-09-01T00:00:00Z"),
      );
      const [summary] = await listConversations(
        db,
        alice,
        new Date("2026-10-01T00:00:00Z"),
      );
      expect(summary?.status).toBe("abandoned");
    });
  });

  describe("stage records", () => {
    it("saves research and learning material once per conversation", async () => {
      const { id } = await createConversation(db, alice);
      await recordMaterial(db, id, {
        original: "# One",
        simplified: null,
        view: "original",
      });
      await recordMaterial(db, id, {
        original: "# One",
        simplified: "# Simple",
        view: "simplified",
      });
      expect((await getConversation(db, alice, id))?.stage).toBe("material");
    });

    it("starts an attempt for a quiz and closes it when graded", async () => {
      const { id } = await createConversation(db, alice);
      await recordQuiz(db, id, QUIZ);
      expect(await listQuizAttempts(db, id)).toMatchObject([
        { attemptNo: 1, status: "in_progress", questionCount: 2, score: null },
      ]);

      await recordEvaluation(db, id, GRADED);
      expect(await listQuizAttempts(db, id)).toMatchObject([
        {
          attemptNo: 1,
          status: "submitted",
          answeredCount: 2,
          score: { percent: 50, tier: "Practitioner" },
        },
      ]);
      expect(await getConversation(db, alice, id)).toMatchObject({
        stage: "evaluation",
        status: "completed",
        score: { percent: 50, tier: "Practitioner" },
      });
    });

    it("records a retake of a graded quiz as a new attempt", async () => {
      const { id } = await createConversation(db, alice);
      await recordQuiz(db, id, QUIZ);
      await recordEvaluation(db, id, GRADED);
      await recordEvaluation(db, id, {
        ...GRADED,
        score: { percent: 100, tier: "Master" },
      });

      const attempts = await listQuizAttempts(db, id);
      expect(attempts.map(({ attemptNo }) => attemptNo)).toEqual([1, 2]);
      expect((await getConversation(db, alice, id))?.score).toEqual({
        percent: 100,
        tier: "Master",
      });
    });

    it("keeps the answers picked so far in the open attempt", async () => {
      const { id } = await createConversation(db, alice);
      expect(await getDraftAnswers(db, id)).toBeNull();
      await recordQuiz(db, id, QUIZ);

      expect(
        await saveDraftAnswers(db, id, { quizId: QUIZ.id, answers: { q1: 1 } }),
      ).toBe(true);
      expect(await getDraftAnswers(db, id)).toEqual({
        quizId: QUIZ.id,
        answers: { q1: 1 },
      });
      expect(await listQuizAttempts(db, id)).toMatchObject([
        { attemptNo: 1, status: "in_progress", answeredCount: 1 },
      ]);
    });

    it("keeps only answers to the quiz's questions, with options that exist", async () => {
      const { id } = await createConversation(db, alice);
      await recordQuiz(db, id, QUIZ);

      await saveDraftAnswers(db, id, {
        quizId: QUIZ.id,
        answers: { q1: 1, q2: 5, q9: 0 },
      });
      expect((await getDraftAnswers(db, id))?.answers).toEqual({ q1: 1 });
      expect(
        await saveDraftAnswers(db, id, { quizId: "quiz_0", answers: {} }),
      ).toBe(false);
    });

    it("opens one new attempt for a retake, which grading closes", async () => {
      const { id } = await createConversation(db, alice);
      await recordQuiz(db, id, QUIZ);
      await recordEvaluation(db, id, GRADED);
      expect(await getDraftAnswers(db, id)).toBeNull();

      await saveDraftAnswers(db, id, { quizId: QUIZ.id, answers: {} });
      await saveDraftAnswers(db, id, { quizId: QUIZ.id, answers: { q2: 0 } });
      expect(await listQuizAttempts(db, id)).toMatchObject([
        { attemptNo: 1, status: "submitted" },
        { attemptNo: 2, status: "in_progress", answeredCount: 1 },
      ]);

      await recordEvaluation(db, id, GRADED);
      expect(await listQuizAttempts(db, id)).toMatchObject([
        { attemptNo: 1, status: "submitted" },
        { attemptNo: 2, status: "submitted", answeredCount: 2 },
      ]);
      expect(await getDraftAnswers(db, id)).toBeNull();
    });

    it("keeps the answer key sealed and out of the attempt list", async () => {
      const { id } = await createConversation(db, alice);
      await recordQuiz(db, id, QUIZ);

      const [row] = await db.select().from(quizAttempts);
      expect(row?.answerKey).toBe("sealed-key");
      expect(JSON.stringify(await listQuizAttempts(db, id))).not.toContain(
        "sealed-key",
      );
    });

    it("removes a conversation's rows with it", async () => {
      const { id } = await createConversation(db, alice);
      await recordResearch(db, id, { topic: "closures", research: RESEARCH });
      await recordQuiz(db, id, QUIZ);

      expect(await deleteConversation(db, alice, id)).toBe(true);
      expect(await listQuizAttempts(db, id)).toEqual([]);
      expect(await db.select().from(quizAttempts)).toEqual([]);
    });
  });

  describe("settings", () => {
    it("is null until saved, then the saved settings", async () => {
      expect(await getUserSettings(db, alice)).toBeNull();

      const settings = {
        questionCount: 7,
        learningLevel: "advanced" as const,
        theme: "dark" as const,
      };
      await saveUserSettings(db, alice, settings);
      await saveUserSettings(db, alice, { ...settings, questionCount: 8 });
      expect(await getUserSettings(db, alice)).toEqual({
        ...settings,
        questionCount: 8,
      });
      expect(await getUserSettings(db, bob)).toBeNull();
    });
  });
});
