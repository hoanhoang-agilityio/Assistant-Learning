import { recordEvaluation, recordQuiz, recordResearch } from "@repo/db";
import { EMPTY_STUDENT_MEMORY } from "@repo/shared/constants/memory";
import type {
  ConversationSummary,
  Quiz,
  StudentMemory,
} from "@repo/shared/schemas";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UNAUTHORIZED_STATUS } from "@/constants/auth";
import {
  BAD_REQUEST_STATUS,
  MEMORY_API_PATH,
  MEMORY_NOT_FOUND_STATUS,
  NO_CONTENT_STATUS,
} from "@/features/memory/constants/memory";
import { learningMemory } from "@/features/memory/services/learning-memory";
import {
  resetTestDatabase,
  testDatabase,
} from "@/services/__tests__/database-mock";

const { auth, currentUser } = vi.hoisted(() => ({
  auth: vi.fn(),
  currentUser: vi.fn(async () => null),
}));

vi.mock("@clerk/nextjs/server", () => ({ auth, currentUser }));
vi.mock("@repo/db/client", () =>
  import("@/services/__tests__/database-mock").then((m) => m.CLIENT_MOCK),
);
vi.mock("@repo/db/checkpointer", () =>
  import("@/services/__tests__/database-mock").then((m) => m.CHECKPOINTER_MOCK),
);

const memory = await import("@/app/api/memory/route");
const item = await import("@/app/api/memory/[kind]/[id]/route");
const conversations = await import("@/app/api/conversations/route");
const conversation = await import("@/app/api/conversations/[id]/route");

const URL_BASE = `http://localhost${MEMORY_API_PATH}`;
const ALICE = "user_alice";
const BOB = "user_bob";
const NO_CONTEXT = {};

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

const GRADED = {
  quiz: { ...QUIZ, answers: { q1: 0, q2: 1 }, submitted: true },
  evaluation: {
    correct: 1,
    total: 2,
    percent: 50,
    weakestConcept: "Scope",
    perQuestion: [],
    mastery: [
      { concept: "Scope", percent: 0 },
      { concept: "Closures", percent: 100 },
    ],
  },
  score: { percent: 50, tier: "Practitioner" as const },
  feedback: { a2uiOperations: [], summary: "Review scope." },
};

const signInAs = (userId: string) =>
  auth.mockResolvedValue({ isAuthenticated: true, userId });

const paramsOf = <T extends object>(params: T) => ({
  params: Promise.resolve(params),
});

const readMemory = async (): Promise<StudentMemory> => {
  const response = await memory.GET(new Request(URL_BASE), NO_CONTEXT);
  return (await response.json()) as StudentMemory;
};

const patchProfile = (body: unknown) =>
  memory.PATCH(
    new Request(URL_BASE, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
    NO_CONTEXT,
  );

const forget = (kind: string, id: string) =>
  item.DELETE(
    new Request(`${URL_BASE}/${kind}/${id}`, { method: "DELETE" }),
    paramsOf({ kind, id }),
  );

/** A conversation of the signed-in user's on closures, with a graded quiz. */
const studyClosures = async (): Promise<string> => {
  const response = await conversations.POST(
    new Request("http://localhost/api/conversations", { method: "POST" }),
    NO_CONTEXT,
  );
  const { id } = (await response.json()) as ConversationSummary;
  const db = testDatabase.current!;
  await recordResearch(db, id, {
    topic: "closures",
    research: {
      title: "Closures",
      summary: "s",
      keyInsight: "k",
      keyTerms: [],
      sources: [],
    },
  });
  await recordQuiz(db, id, QUIZ);
  await recordEvaluation(db, id, GRADED);
  return id;
};

beforeEach(async () => {
  auth.mockReset();
  await resetTestDatabase();
});

describe("/api/memory", () => {
  it("needs a signed-in user on every route", async () => {
    auth.mockResolvedValue({ isAuthenticated: false, userId: null });

    const responses = [
      await memory.GET(new Request(URL_BASE), NO_CONTEXT),
      await patchProfile({ style: "short" }),
      await forget("profile", "style"),
    ];
    expect(responses.map(({ status }) => status)).toEqual([
      UNAUTHORIZED_STATUS,
      UNAUTHORIZED_STATUS,
      UNAUTHORIZED_STATUS,
    ]);
  });

  it("is empty for a new student", async () => {
    signInAs(ALICE);

    expect(await readMemory()).toEqual(EMPTY_STUDENT_MEMORY);
  });

  it("shows what the agent learned and the graded attempts, to their owner only", async () => {
    signInAs(ALICE);
    const id = await studyClosures();
    await learningMemory.saveProfile(ALICE, { language: "Vietnamese" });

    const alice = await readMemory();
    expect(alice.profile.language).toBe("Vietnamese");
    expect(alice.concepts.map(({ key, percent }) => [key, percent])).toEqual([
      ["scope", 0],
      ["closures", 100],
    ]);
    expect(alice.topics).toMatchObject([
      { conversationId: id, topic: "closures", bestPercent: 50 },
    ]);
    expect(await learningMemory.load(ALICE)).toEqual(alice);

    signInAs(BOB);
    expect(await readMemory()).toEqual(EMPTY_STUDENT_MEMORY);
    expect(await learningMemory.load(BOB)).toEqual(EMPTY_STUDENT_MEMORY);
  });

  it("lets the student edit the profile, and forget a field with null", async () => {
    signInAs(ALICE);

    const edited = await patchProfile({ level: "advanced", style: "code" });
    expect(edited.status).toBe(200);
    expect(await edited.json()).toEqual({
      profile: { level: "advanced", style: "code", language: null },
    });

    await patchProfile({ style: null });
    expect((await readMemory()).profile).toEqual({
      level: "advanced",
      style: null,
      language: null,
    });
  });

  it("keeps the student's own setting from what a run learns, until they forget it", async () => {
    signInAs(ALICE);
    await patchProfile({ language: "English" });

    await learningMemory.saveProfile(ALICE, {
      language: "French",
      level: "beginner",
    });
    expect((await readMemory()).profile).toMatchObject({
      language: "English",
      level: "beginner",
    });

    await forget("profile", "language");
    await learningMemory.saveProfile(ALICE, { language: "French" });
    expect((await readMemory()).profile.language).toBe("French");
  });

  it("refuses a profile edit it cannot read", async () => {
    signInAs(ALICE);

    for (const body of [{}, { level: "expert" }, { style: "" }, "nope"]) {
      expect((await patchProfile(body)).status).toBe(BAD_REQUEST_STATUS);
    }
  });

  it("forgets one profile field, concept or topic", async () => {
    signInAs(ALICE);
    const id = await studyClosures();
    await patchProfile({ level: "advanced", language: "Vietnamese" });

    expect((await forget("profile", "language")).status).toBe(
      NO_CONTENT_STATUS,
    );
    expect((await forget("concepts", "scope")).status).toBe(NO_CONTENT_STATUS);
    expect((await forget("topics", id)).status).toBe(NO_CONTENT_STATUS);

    const left = await readMemory();
    expect(left.profile).toEqual({
      level: "advanced",
      style: null,
      language: null,
    });
    expect(left.concepts.map(({ key }) => key)).toEqual(["closures"]);
    expect(left.topics).toEqual([]);
  });

  it("answers 404 for what is not kept or not theirs", async () => {
    signInAs(ALICE);
    const id = await studyClosures();

    signInAs(BOB);
    const statuses = [
      await forget("concepts", "scope"),
      await forget("topics", id),
      await forget("profile", "age"),
      await forget("passwords", "x"),
    ].map(({ status }) => status);
    expect(statuses.every((status) => status === MEMORY_NOT_FOUND_STATUS)).toBe(
      true,
    );

    signInAs(ALICE);
    expect((await readMemory()).concepts).toHaveLength(2);
  });

  it("rebuilds concepts and drops the topic when a conversation is deleted", async () => {
    signInAs(ALICE);
    const id = await studyClosures();

    await conversation.DELETE(
      new Request(`http://localhost/api/conversations/${id}`, {
        method: "DELETE",
      }),
      paramsOf({ id }),
    );

    const left = await readMemory();
    expect(left.concepts).toEqual([]);
    expect(left.topics).toEqual([]);
  });
});
