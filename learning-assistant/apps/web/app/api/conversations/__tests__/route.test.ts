import { recordConversationRun, recordQuiz, recordResearch } from "@repo/db";
import type { ConversationSummary, Quiz } from "@repo/shared/schemas";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UNAUTHORIZED_STATUS } from "@/constants/auth";
import {
  API_KEY_HEADER,
  API_KEY_SEAL_SECRET_ENV_KEY,
} from "@/features/api-key/constants/api-key";
import { sealApiKey } from "@/features/api-key/services/sealed-api-key";
import {
  BAD_REQUEST_STATUS,
  CONVERSATION_NOT_FOUND_STATUS,
  CREATED_STATUS,
  MISSING_API_KEY_STATUS,
  NO_CONTENT_STATUS,
  TITLE_FAILED_STATUS,
} from "@/features/conversations/constants/conversations";
import {
  resetTestDatabase,
  testDatabase,
} from "@/services/__tests__/database-mock";

const { auth, currentUser, summarizeTitle } = vi.hoisted(() => ({
  auth: vi.fn(),
  summarizeTitle: vi.fn(),
  currentUser: vi.fn(async () => ({
    primaryEmailAddress: { emailAddress: "alice@example.com" },
  })),
}));

vi.mock("@clerk/nextjs/server", () => ({ auth, currentUser }));
vi.mock("@repo/agent", () => ({ summarizeTitle }));
vi.mock("@repo/db/client", () =>
  import("@/services/__tests__/database-mock").then((m) => m.CLIENT_MOCK),
);
vi.mock("@repo/db/checkpointer", () =>
  import("@/services/__tests__/database-mock").then((m) => m.CHECKPOINTER_MOCK),
);

const list = await import("@/app/api/conversations/route");
const one = await import("@/app/api/conversations/[id]/route");
const attempts = await import("@/app/api/conversations/[id]/attempts/route");
const answers = await import("@/app/api/conversations/[id]/answers/route");
const title = await import("@/app/api/conversations/[id]/title/route");

const URL_BASE = "http://localhost/api/conversations";
const SEAL_SECRET = "test-seal-secret";
const API_KEY = "sk-title-route";
const FIRST_MESSAGE = "Can you teach me how closures work in JavaScript?";

const QUIZ: Quiz = {
  id: "quiz_1",
  questions: [
    { id: "q1", concept: "Scope", question: "Q?", options: ["a", "b"] },
  ],
  answers: {},
  answerKeySealed: "sealed-key",
  submitted: false,
};

const signInAs = (userId: string) =>
  auth.mockResolvedValue({ isAuthenticated: true, userId });

const paramsOf = (id: string) => ({ params: Promise.resolve({ id }) });

const create = async (): Promise<ConversationSummary> => {
  const response = await list.POST(
    new Request(URL_BASE, { method: "POST" }),
    {},
  );
  expect(response.status).toBe(CREATED_STATUS);
  return (await response.json()) as ConversationSummary;
};

const listIds = async (): Promise<string[]> => {
  const response = await list.GET(new Request(URL_BASE), {});
  const body = (await response.json()) as {
    conversations: ConversationSummary[];
  };
  return body.conversations.map(({ id }) => id);
};

const rename = (id: string, title: unknown) =>
  one.PATCH(
    new Request(`${URL_BASE}/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
    paramsOf(id),
  );

const remove = (id: string) =>
  one.DELETE(
    new Request(`${URL_BASE}/${id}`, { method: "DELETE" }),
    paramsOf(id),
  );

/** Writes a checkpoint for the thread, as a run would. */
const checkpointThread = async (threadId: string) => {
  const { checkpointer } = testDatabase;
  await checkpointer.put(
    { configurable: { thread_id: threadId, checkpoint_ns: "" } },
    {
      v: 4,
      id: "checkpoint-1",
      ts: new Date().toISOString(),
      channel_values: {},
      channel_versions: {},
      versions_seen: {},
    },
    { source: "input", step: -1, parents: {} },
  );
};

const saveAnswers = (id: string, body: unknown) =>
  answers.PUT(
    new Request(`${URL_BASE}/${id}/answers`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
    paramsOf(id),
  );

const readAnswers = async (id: string) =>
  answers.GET(new Request(`${URL_BASE}/${id}/answers`), paramsOf(id));

const nameByFirstMessage = (
  id: string,
  body: unknown,
  sealedKey: string | null = sealApiKey(API_KEY, SEAL_SECRET),
) =>
  title.POST(
    new Request(`${URL_BASE}/${id}/title`, {
      method: "POST",
      headers: sealedKey ? { [API_KEY_HEADER]: sealedKey } : {},
      body: JSON.stringify(body),
    }),
    paramsOf(id),
  );

const readCheckpoint = (threadId: string) =>
  testDatabase.checkpointer.getTuple({ configurable: { thread_id: threadId } });

beforeEach(async () => {
  auth.mockReset();
  summarizeTitle.mockReset();
  summarizeTitle.mockResolvedValue("JavaScript closures");
  vi.stubEnv(API_KEY_SEAL_SECRET_ENV_KEY, SEAL_SECRET);
  await resetTestDatabase();
  signInAs("alice");
});

describe("/api/conversations", () => {
  it("answers 401 without a session", async () => {
    auth.mockResolvedValue({ isAuthenticated: false, userId: null });

    expect((await list.GET(new Request(URL_BASE), {})).status).toBe(
      UNAUTHORIZED_STATUS,
    );
    expect((await remove("x")).status).toBe(UNAUTHORIZED_STATUS);
    expect((await readAnswers("x")).status).toBe(UNAUTHORIZED_STATUS);
    expect((await saveAnswers("x", {})).status).toBe(UNAUTHORIZED_STATUS);
  });

  it("keeps the answers picked so far for the conversation's quiz", async () => {
    const { id } = await create();
    expect(await (await readAnswers(id)).json()).toEqual({ draft: null });
    await recordQuiz(testDatabase.current!, id, QUIZ);

    const saved = await saveAnswers(id, {
      quizId: QUIZ.id,
      answers: { q1: 1 },
    });
    expect(saved.status).toBe(NO_CONTENT_STATUS);
    expect(await (await readAnswers(id)).json()).toEqual({
      draft: { quizId: QUIZ.id, answers: { q1: 1 } },
    });
  });

  it("refuses answers it cannot read, or for a quiz it does not have", async () => {
    const { id } = await create();
    await recordQuiz(testDatabase.current!, id, QUIZ);

    for (const body of [
      {},
      { quizId: QUIZ.id },
      { quizId: QUIZ.id, answers: { q1: -1 } },
    ]) {
      expect((await saveAnswers(id, body)).status).toBe(BAD_REQUEST_STATUS);
    }
    expect(
      (await saveAnswers(id, { quizId: "quiz_0", answers: {} })).status,
    ).toBe(CONVERSATION_NOT_FOUND_STATUS);
  });

  it("creates a conversation for a new topic and lists it", async () => {
    const created = await create();

    expect(created).toMatchObject({
      title: null,
      stage: "idle",
      status: "active",
      score: null,
    });
    expect(await listIds()).toEqual([created.id]);
  });

  it("renames a conversation", async () => {
    const { id } = await create();

    const response = await rename(id, "  Closures  ");

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ id, title: "Closures" });
  });

  it("refuses an empty or too long title", async () => {
    const { id } = await create();

    expect((await rename(id, " ")).status).toBe(BAD_REQUEST_STATUS);
    expect((await rename(id, "x".repeat(200))).status).toBe(BAD_REQUEST_STATUS);
  });

  it("names a new conversation by a title summarised from its first message", async () => {
    const { id } = await create();

    const response = await nameByFirstMessage(id, { message: FIRST_MESSAGE });

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      id,
      title: "JavaScript closures",
    });
    expect(summarizeTitle).toHaveBeenCalledWith({
      apiKey: API_KEY,
      userText: FIRST_MESSAGE,
    });
  });

  it("replaces the first message a finished run named it by", async () => {
    const { id } = await create();
    await recordConversationRun(testDatabase.current!, id, {
      stage: "idle",
      userText: FIRST_MESSAGE,
    });

    const response = await nameByFirstMessage(id, { message: FIRST_MESSAGE });

    expect(await response.json()).toMatchObject({
      title: "JavaScript closures",
    });
  });

  it("keeps another name without calling the model", async () => {
    const { id } = await create();
    await recordResearch(testDatabase.current!, id, {
      topic: "closures",
      research: {
        title: "Closures in depth",
        summary: "s",
        keyInsight: "k",
        keyTerms: [],
        sources: [],
      },
    });

    const response = await nameByFirstMessage(id, { message: FIRST_MESSAGE });

    expect(await response.json()).toMatchObject({ title: "Closures in depth" });
    expect(summarizeTitle).not.toHaveBeenCalled();
  });

  it("refuses to name without a message, a key, or the conversation", async () => {
    const { id } = await create();

    expect((await nameByFirstMessage(id, { message: " " })).status).toBe(
      BAD_REQUEST_STATUS,
    );
    expect(
      (await nameByFirstMessage(id, { message: FIRST_MESSAGE }, null)).status,
    ).toBe(MISSING_API_KEY_STATUS);
    signInAs("bob");
    expect(
      (await nameByFirstMessage(id, { message: FIRST_MESSAGE })).status,
    ).toBe(CONVERSATION_NOT_FOUND_STATUS);
    expect(summarizeTitle).not.toHaveBeenCalled();
  });

  it("answers 502 and keeps the conversation untitled when the model fails", async () => {
    const { id } = await create();
    summarizeTitle.mockRejectedValue(new Error("model down"));
    vi.spyOn(console, "error").mockImplementation(() => {});

    const response = await nameByFirstMessage(id, { message: FIRST_MESSAGE });

    expect(response.status).toBe(TITLE_FAILED_STATUS);
    expect(
      await (
        await one.GET(new Request(`${URL_BASE}/${id}`), paramsOf(id))
      ).json(),
    ).toMatchObject({ title: null });
  });

  it("deletes a conversation with its thread's checkpoints", async () => {
    const { id } = await create();
    await checkpointThread(id);
    expect(await readCheckpoint(id)).toBeDefined();

    expect((await remove(id)).status).toBe(NO_CONTENT_STATUS);

    expect(await readCheckpoint(id)).toBeUndefined();
    expect(await listIds()).toEqual([]);
  });

  it("lists a conversation's attempts without the answer key", async () => {
    const { id } = await create();
    await recordQuiz(testDatabase.current!, id, QUIZ);

    const response = await attempts.GET(
      new Request(`${URL_BASE}/${id}/attempts`),
      paramsOf(id),
    );
    const text = await response.text();

    expect(JSON.parse(text)).toMatchObject({
      attempts: [{ attemptNo: 1, status: "in_progress", questionCount: 1 }],
    });
    expect(text).not.toContain("sealed-key");
  });

  it("keeps another user out of a conversation and its thread", async () => {
    const { id } = await create();
    await checkpointThread(id);
    signInAs("bob");

    expect(await listIds()).toEqual([]);
    expect(
      (await one.GET(new Request(`${URL_BASE}/${id}`), paramsOf(id))).status,
    ).toBe(CONVERSATION_NOT_FOUND_STATUS);
    expect((await rename(id, "Mine")).status).toBe(
      CONVERSATION_NOT_FOUND_STATUS,
    );
    expect((await remove(id)).status).toBe(CONVERSATION_NOT_FOUND_STATUS);
    expect(
      (
        await attempts.GET(
          new Request(`${URL_BASE}/${id}/attempts`),
          paramsOf(id),
        )
      ).status,
    ).toBe(CONVERSATION_NOT_FOUND_STATUS);
    expect((await readAnswers(id)).status).toBe(CONVERSATION_NOT_FOUND_STATUS);
    expect(
      (await saveAnswers(id, { quizId: QUIZ.id, answers: {} })).status,
    ).toBe(CONVERSATION_NOT_FOUND_STATUS);
    expect(await readCheckpoint(id)).toBeDefined();
  });

  it("answers 404 for an id that is not a uuid", async () => {
    expect((await remove("thread-1")).status).toBe(
      CONVERSATION_NOT_FOUND_STATUS,
    );
  });
});
