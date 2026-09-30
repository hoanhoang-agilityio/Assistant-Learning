import { v4 as uuidv4 } from "uuid";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UNAUTHORIZED_STATUS } from "@/constants/auth";
import { COPILOT_RUNTIME_URL } from "@/constants/copilot";
import { THREAD_NOT_FOUND_STATUS } from "@/features/threads/constants/threads";

const { auth } = vi.hoisted(() => ({ auth: vi.fn() }));

vi.mock("@clerk/nextjs/server", () => ({ auth }));

const route = await import("@/app/api/copilotkit/[[...slug]]/route");

const METHODS = ["GET", "POST", "PATCH", "DELETE"] as const;

const ENDPOINTS = [
  { method: "GET", path: "/info" },
  { method: "POST", path: "/agent/learning/run" },
  { method: "POST", path: "/agent/learning/connect" },
  { method: "POST", path: "/agent/learning/stop/thread-1" },
] as const;

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

const listThreadIds = async (): Promise<string[]> => {
  const response = await route.GET(
    requestTo("GET", "/threads?agentId=learning"),
  );
  const { threads } = (await response.json()) as { threads: { id: string }[] };
  return threads.map(({ id }) => id);
};

beforeEach(() => {
  auth.mockReset();
});

describe("CopilotKit runtime route without a session", () => {
  beforeEach(() => {
    auth.mockResolvedValue({ isAuthenticated: false, userId: null });
  });

  it.each(METHODS)("%s answers 401", async (method) => {
    const response = await route[method](requestTo(method, "/info"));

    expect(response.status).toBe(UNAUTHORIZED_STATUS);
  });

  it.each(ENDPOINTS)("$method $path answers 401", async ({ method, path }) => {
    const response = await route[method](requestTo(method, path));

    expect(response.status).toBe(UNAUTHORIZED_STATUS);
  });
});

describe("CopilotKit runtime route with a session", () => {
  it("reaches the runtime", async () => {
    auth.mockResolvedValue({ isAuthenticated: true, userId: "user_1" });

    const response = await route.GET(requestTo("GET", "/info"));

    expect(response.status).toBe(200);
  });
});

describe("CopilotKit runtime route with two users", () => {
  const threadId = uuidv4();

  beforeEach(async () => {
    signInAs("alice");
    // No OpenAI key: the run ends at once with the agent's own error, which
    // is enough to create the thread and make Alice its owner.
    const run = await route.POST(
      requestTo("POST", "/agent/learning/run", runInput(threadId)),
    );
    await run.text();
  });

  it("lets the owner list and read the thread", async () => {
    expect(await listThreadIds()).toContain(threadId);

    const messages = await route.GET(
      requestTo("GET", `/threads/${threadId}/messages?agentId=learning`),
    );
    expect(messages.status).toBe(200);
  });

  it("hides the thread from another user on every route", async () => {
    signInAs("bob");

    expect(await listThreadIds()).not.toContain(threadId);
    for (const part of ["messages", "events", "state"]) {
      const response = await route.GET(
        requestTo("GET", `/threads/${threadId}/${part}?agentId=learning`),
      );
      expect(response.status).toBe(THREAD_NOT_FOUND_STATUS);
    }
    const posts = [
      requestTo("POST", "/agent/learning/run", runInput(threadId)),
      requestTo("POST", "/agent/learning/connect", runInput(threadId)),
      requestTo("POST", `/agent/learning/stop/${threadId}`),
    ];
    for (const request of posts) {
      expect((await route.POST(request)).status).toBe(THREAD_NOT_FOUND_STATUS);
    }
  });

  it("never lets anyone clear every thread", async () => {
    const response = await route.POST(requestTo("POST", "/threads/clear"));

    expect(response.status).toBe(THREAD_NOT_FOUND_STATUS);
    expect(await listThreadIds()).toContain(threadId);
  });
});
