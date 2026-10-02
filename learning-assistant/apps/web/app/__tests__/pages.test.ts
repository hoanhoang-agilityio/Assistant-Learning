import { recordEvaluation, recordQuiz, recordResearch } from "@repo/db";
import type {
  ConversationSummary,
  LearningHistory,
  Quiz,
} from "@repo/shared/schemas";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  resetTestDatabase,
  testDatabase,
} from "@/services/__tests__/database-mock";
import { deleteUserData } from "@/services/user-deletion";

const SIGN_IN_REDIRECT = "NEXT_REDIRECT:sign-in";

const { auth, currentUser, redirectToSignIn } = vi.hoisted(() => ({
  auth: vi.fn(),
  currentUser: vi.fn(async () => null),
  redirectToSignIn: vi.fn(() => {
    throw new Error("NEXT_REDIRECT:sign-in");
  }),
}));

vi.mock("@clerk/nextjs/server", () => ({ auth, currentUser }));
// The client root pulls in CopilotKit and its CSS; only its props matter here.
vi.mock("@/components/layout/AppShell", () => ({ AppShell: () => null }));
vi.mock("@repo/db/client", () =>
  import("@/services/__tests__/database-mock").then((m) => m.CLIENT_MOCK),
);
vi.mock("@repo/db/checkpointer", () =>
  import("@/services/__tests__/database-mock").then((m) => m.CHECKPOINTER_MOCK),
);

const HomePage = (await import("@/app/page")).default;
const ApiKeyPage = (await import("@/app/api-key/page")).default;
const MemoryPage = (await import("@/app/memory/page")).default;
const HistoryPage = (await import("@/app/history/page")).default;
const conversations = await import("@/app/api/conversations/route");

const ALICE = "user_alice";
const BOB = "user_bob";
const CONVERSATION_ID = "8c3c5d0e-4f43-4c39-9a51-6f1f0a2b9c11";

const QUIZ: Quiz = {
  id: "quiz_1",
  questions: [
    { id: "q1", concept: "Scope", question: "Q1?", options: ["a", "b"] },
  ],
  answers: {},
  answerKeySealed: "sealed-key",
  submitted: false,
};

const GRADED = {
  quiz: { ...QUIZ, answers: { q1: 0 }, submitted: true },
  evaluation: {
    correct: 1,
    total: 1,
    percent: 100,
    weakestConcept: null,
    perQuestion: [],
    mastery: [{ concept: "Scope", percent: 100 }],
  },
  score: { percent: 100, tier: "Master" as const },
  feedback: { a2uiOperations: [], summary: "Well done." },
};

const signInAs = (userId: string) =>
  auth.mockResolvedValue({ isAuthenticated: true, userId, redirectToSignIn });

const signOut = () =>
  auth.mockResolvedValue({
    isAuthenticated: false,
    userId: null,
    redirectToSignIn,
  });

const searchParamsOf = (params: Record<string, string>) => ({
  searchParams: Promise.resolve(params),
});

/** A conversation of the signed-in user's on `topic`, with a graded quiz. */
const study = async (topic: string): Promise<string> => {
  const response = await conversations.POST(
    new Request("http://localhost/api/conversations", { method: "POST" }),
    {},
  );
  const { id } = (await response.json()) as ConversationSummary;
  const db = testDatabase.current!;
  await recordResearch(db, id, {
    topic,
    research: {
      title: topic,
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

/** The history the page hands its view: `<CenteredPage><HistoryView history /></CenteredPage>`. */
const readHistory = async (): Promise<LearningHistory> => {
  const page = (await HistoryPage()) as ReactElement<{
    children: ReactElement<{ history: LearningHistory }>;
  }>;
  return page.props.children.props.history;
};

beforeEach(async () => {
  auth.mockReset();
  redirectToSignIn.mockClear();
  await resetTestDatabase();
});

describe("pages", () => {
  it.each([
    ["/", () => HomePage(searchParamsOf({}))],
    ["/api-key", () => ApiKeyPage()],
    ["/memory", () => MemoryPage()],
    ["/history", () => HistoryPage()],
  ])("%s sends a signed-out visitor to sign in", async (_, render) => {
    signOut();

    await expect(render()).rejects.toThrow(SIGN_IN_REDIRECT);
    expect(redirectToSignIn).toHaveBeenCalledOnce();
  });

  it("/history shows only the signed-in user's topics", async () => {
    signInAs(ALICE);
    const alices = await study("Closures");
    signInAs(BOB);
    const bobs = await study("Recursion");

    expect(
      (await readHistory()).topics.map(({ conversationId }) => conversationId),
    ).toEqual([bobs]);
    signInAs(ALICE);
    expect(
      (await readHistory()).topics.map(({ conversationId }) => conversationId),
    ).toEqual([alices]);
  });

  it("/history shows a deleted user's session nothing of theirs", async () => {
    signInAs(ALICE);
    await study("Closures");

    await deleteUserData(ALICE);

    expect(await readHistory()).toEqual({ topics: [] });
  });

  it("/ hands on a retake only for a conversation id", async () => {
    signInAs(ALICE);
    const retakeOf = async (retake: string) =>
      (
        (await HomePage(searchParamsOf({ retake }))) as ReactElement<{
          retakeId: string | null;
        }>
      ).props.retakeId;

    expect(await retakeOf(CONVERSATION_ID)).toBe(CONVERSATION_ID);
    expect(await retakeOf("../api/memory")).toBeNull();
  });
});
