import type { ConversationSummary } from "@repo/shared/schemas";
import { v4 as uuidv4 } from "uuid";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UNAUTHORIZED_STATUS } from "@/constants/auth";
import { COPILOT_RUNTIME_URL } from "@/constants/copilot";
import { THREAD_NOT_FOUND_STATUS } from "@/features/conversations/constants/threads";
import { resetTestDatabase } from "@/services/__tests__/database-mock";

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

const route = await import("@/app/api/copilotkit/[[...slug]]/route");
const conversations = await import("@/app/api/conversations/route");

const METHODS = ["GET", "POST", "PATCH", "DELETE"] as const;

const ENDPOINTS = [
  { method: "GET", path: "/info" },
  { method: "POST", path: "/agent/learning/run" },
  { method: "POST", path: "/agent/learning/connect" },
  { method: "POST", path: "/agent/learning/stop/thread-1" },
] as const;

/** Runtime routes take no params of their own. */
const NO_CONTEXT = {};

const requestTo = (method: string, path: string, body: unknown = {}) =>
  new Request(`http://localhost${COPILOT_RUNTIME_URL}${path}`, {
    method,
    headers: { "content-type": "application/json" },
    ...(method === "GET" ? {} : { body: JSON.stringify(body) }),
  });

const signInAs = (userId: string) =>
  auth.mockResolvedValue({ isAuthenticated: true, userId });

/** A run request for `threadId`, as the chat sends it. */
const runInput = (threadId: string) => ({
  threadId,
  runId: uuidv4(),
  state: {},
  messages: [{ id: uuidv4(), role: "user", content: "hi" }],
  tools: [],
  context: [],
  forwardedProps: {},
});

/** "New topic": the signed-in user's new conversation. */
const createConversation = async (): Promise<string> => {
  const response = await conversations.POST(
    new Request("http://localhost/api/conversations", { method: "POST" }),
    NO_CONTEXT,
  );
  return ((await response.json()) as ConversationSummary).id;
};

const listThreadIds = async (): Promise<string[]> => {
  const response = await route.GET(
    requestTo("GET", "/threads?agentId=learning"),
    NO_CONTEXT,
  );
  const { threads } = (await response.json()) as { threads: { id: string }[] };
  return threads.map(({ id }) => id);
};

beforeEach(async () => {
  auth.mockReset();
  await resetTestDatabase();
});

describe("CopilotKit runtime route without a session", () => {
  beforeEach(() => {
    auth.mockResolvedValue({ isAuthenticated: false, userId: null });
  });

  it.each(METHODS)("%s answers 401", async (method) => {
    const response = await route[method](
      requestTo(method, "/info"),
      NO_CONTEXT,
    );

    expect(response.status).toBe(UNAUTHORIZED_STATUS);
  });

  it.each(ENDPOINTS)("$method $path answers 401", async ({ method, path }) => {
    const response = await route[method](requestTo(method, path), NO_CONTEXT);

    expect(response.status).toBe(UNAUTHORIZED_STATUS);
  });
});

describe("CopilotKit runtime route with a session", () => {
  it("reaches the runtime", async () => {
    signInAs("user_1");

    const response = await route.GET(requestTo("GET", "/info"), NO_CONTEXT);

    expect(response.status).toBe(200);
  });

  it("refuses a thread that is no conversation", async () => {
    signInAs("user_1");

    const response = await route.POST(
      requestTo("POST", "/agent/learning/run", runInput(uuidv4())),
      NO_CONTEXT,
    );

    expect(response.status).toBe(THREAD_NOT_FOUND_STATUS);
  });
});

describe("CopilotKit runtime route with two users", () => {
  let threadId: string;

  beforeEach(async () => {
    signInAs("alice");
    threadId = await createConversation();
    // No OpenAI key: the run ends at once with the agent's own error, which
    // is enough for the runtime to hold the thread.
    const run = await route.POST(
      requestTo("POST", "/agent/learning/run", runInput(threadId)),
      NO_CONTEXT,
    );
    await run.text();
  });

  it("lets the owner list and read the thread", async () => {
    expect(await listThreadIds()).toContain(threadId);

    const messages = await route.GET(
      requestTo("GET", `/threads/${threadId}/messages?agentId=learning`),
      NO_CONTEXT,
    );
    expect(messages.status).toBe(200);
  });

  it("hides the thread from another user on every route", async () => {
    signInAs("bob");

    expect(await listThreadIds()).not.toContain(threadId);
    for (const part of ["messages", "events", "state"]) {
      const response = await route.GET(
        requestTo("GET", `/threads/${threadId}/${part}?agentId=learning`),
        NO_CONTEXT,
      );
      expect(response.status).toBe(THREAD_NOT_FOUND_STATUS);
    }
    const posts = [
      requestTo("POST", "/agent/learning/run", runInput(threadId)),
      requestTo("POST", "/agent/learning/connect", runInput(threadId)),
      requestTo("POST", `/agent/learning/stop/${threadId}`),
    ];
    for (const request of posts) {
      expect((await route.POST(request, NO_CONTEXT)).status).toBe(
        THREAD_NOT_FOUND_STATUS,
      );
    }
  });

  it("never lets anyone clear every thread", async () => {
    const response = await route.POST(
      requestTo("POST", "/threads/clear"),
      NO_CONTEXT,
    );

    expect(response.status).toBe(THREAD_NOT_FOUND_STATUS);
    expect(await listThreadIds()).toContain(threadId);
  });
});
