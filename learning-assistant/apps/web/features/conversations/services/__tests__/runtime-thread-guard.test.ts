import type { RouteInfo } from "@copilotkit/runtime/v2";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UNAUTHORIZED_STATUS } from "@/constants/auth";
import { TOO_MANY_REQUESTS_STATUS } from "@/constants/rate-limit";
import { THREAD_NOT_FOUND_STATUS } from "@/features/conversations/constants/threads";
import { createThreadGuardHooks } from "@/features/conversations/services/runtime-thread-guard";
import type { ThreadOwners } from "@/features/conversations/types/threads";
import { createRateLimiter } from "@/services/rate-limit";

vi.mock("@clerk/nextjs/server", () => ({ auth: vi.fn() }));

/** Conversations as the table holds them: thread id → owner. */
const OWNERS = new Map([
  ["t1", "alice"],
  ["t2", "bob"],
]);

const owners: ThreadOwners = {
  getOwner: async (threadId) => OWNERS.get(threadId),
  filterOwned: async (userId, threadIds) =>
    new Set(threadIds.filter((id) => OWNERS.get(id) === userId)),
};

let currentUser: string | null;
let hooks: ReturnType<typeof createThreadGuardHooks>;

const request = (body?: unknown) =>
  new Request("http://localhost/api/copilotkit/x", {
    method: body === undefined ? "GET" : "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

/** Runs the before-handler hook; resolves to the short-circuit status, or `null` when it lets the request through. */
const statusFor = async (route: RouteInfo, body?: unknown) => {
  try {
    await hooks.onBeforeHandler?.({
      route,
      request: request(body),
      path: "/x",
      runtime: {} as never,
    });
    return null;
  } catch (thrown) {
    if (thrown instanceof Response) {
      return thrown.status;
    }
    throw thrown;
  }
};

const run = { method: "agent/run", agentId: "learning" } as const;
const connect = { method: "agent/connect", agentId: "learning" } as const;

beforeEach(() => {
  currentUser = "alice";
  hooks = createThreadGuardHooks({
    getUserId: async () => currentUser,
    owners,
    runLimiter: createRateLimiter({ limit: 2, windowMs: 60_000 }),
  });
});

describe("onBeforeHandler", () => {
  it("lets the owner run, open, stop and read their conversation", async () => {
    expect(await statusFor(run, { threadId: "t1" })).toBeNull();
    expect(await statusFor(connect, { threadId: "t1" })).toBeNull();
    expect(
      await statusFor({
        method: "agent/stop",
        agentId: "learning",
        threadId: "t1",
      }),
    ).toBeNull();
    expect(
      await statusFor({ method: "threads/messages", threadId: "t1" }),
    ).toBeNull();
  });

  it("answers 404 to another user on every route about that thread", async () => {
    currentUser = "bob";

    expect(await statusFor(run, { threadId: "t1" })).toBe(
      THREAD_NOT_FOUND_STATUS,
    );
    expect(await statusFor(connect, { threadId: "t1" })).toBe(
      THREAD_NOT_FOUND_STATUS,
    );
    for (const method of [
      "threads/messages",
      "threads/events",
      "threads/state",
    ] as const) {
      expect(await statusFor({ method, threadId: "t1" })).toBe(
        THREAD_NOT_FOUND_STATUS,
      );
    }
    expect(
      await statusFor({
        method: "agent/stop",
        agentId: "learning",
        threadId: "t1",
      }),
    ).toBe(THREAD_NOT_FOUND_STATUS);
  });

  it("answers 404 for a thread no conversation has, and creates nothing", async () => {
    expect(await statusFor(run, { threadId: "made-up" })).toBe(
      THREAD_NOT_FOUND_STATUS,
    );
    expect(await statusFor(connect, { threadId: "made-up" })).toBe(
      THREAD_NOT_FOUND_STATUS,
    );
    expect(OWNERS.has("made-up")).toBe(false);
  });

  it("never allows clearing every thread", async () => {
    expect(await statusFor({ method: "threads/clear" })).toBe(
      THREAD_NOT_FOUND_STATUS,
    );
  });

  it("answers 401 without a user", async () => {
    currentUser = null;

    expect(await statusFor(run, { threadId: "t1" })).toBe(UNAUTHORIZED_STATUS);
  });

  it("answers 429 once a user starts too many runs, and only for runs", async () => {
    expect(await statusFor(run, { threadId: "t1" })).toBeNull();
    expect(await statusFor(run, { threadId: "t1" })).toBeNull();
    expect(await statusFor(run, { threadId: "t1" })).toBe(
      TOO_MANY_REQUESTS_STATUS,
    );
    expect(await statusFor(connect, { threadId: "t1" })).toBeNull();

    currentUser = "bob";
    expect(await statusFor(run, { threadId: "t2" })).toBeNull();
  });
});

describe("onResponse", () => {
  it("lists only the caller's threads", async () => {
    const listed = Response.json({
      threads: [{ id: "t1" }, { id: "t2" }, { id: "nobody" }],
      nextCursor: null,
    });

    const response = await hooks.onResponse?.({
      route: { method: "threads/list" },
      response: listed,
      request: request(),
      path: "/threads",
      runtime: {} as never,
    });

    expect(await response?.json()).toEqual({
      threads: [{ id: "t1" }],
      nextCursor: null,
    });
  });

  it("leaves other responses alone", async () => {
    const response = await hooks.onResponse?.({
      route: { method: "info" },
      response: Response.json({}),
      request: request(),
      path: "/info",
      runtime: {} as never,
    });

    expect(response).toBeUndefined();
  });
});
