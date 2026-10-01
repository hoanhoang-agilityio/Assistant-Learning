import { recordQuiz } from "@repo/db";
import type { ConversationSummary, Quiz } from "@repo/shared/schemas";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UNAUTHORIZED_STATUS } from "@/constants/auth";
import {
  BAD_REQUEST_STATUS,
  CONVERSATION_NOT_FOUND_STATUS,
  CREATED_STATUS,
  NO_CONTENT_STATUS,
} from "@/features/conversations/constants/conversations";
import {
  resetTestDatabase,
  testDatabase,
} from "@/services/__tests__/database-mock";

const { auth, currentUser } = vi.hoisted(() => ({
  auth: vi.fn(),
  currentUser: vi.fn(async () => ({
    primaryEmailAddress: { emailAddress: "alice@example.com" },
  })),
}));

vi.mock("@clerk/nextjs/server", () => ({ auth, currentUser }));
vi.mock("@repo/db/client", () =>
  import("@/services/__tests__/database-mock").then((m) => m.CLIENT_MOCK),
);
vi.mock("@repo/db/checkpointer", () =>
  import("@/services/__tests__/database-mock").then((m) => m.CHECKPOINTER_MOCK),
);

const list = await import("@/app/api/conversations/route");
const one = await import("@/app/api/conversations/[id]/route");
const attempts = await import("@/app/api/conversations/[id]/attempts/route");

const URL_BASE = "http://localhost/api/conversations";

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

const readCheckpoint = (threadId: string) =>
  testDatabase.checkpointer.getTuple({ configurable: { thread_id: threadId } });

beforeEach(async () => {
  auth.mockReset();
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
    expect(await readCheckpoint(id)).toBeDefined();
  });

  it("answers 404 for an id that is not a uuid", async () => {
    expect((await remove("thread-1")).status).toBe(
      CONVERSATION_NOT_FOUND_STATUS,
    );
  });
});
