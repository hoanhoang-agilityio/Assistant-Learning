import type { RouteInfo } from "@copilotkit/runtime/v2";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UNAUTHORIZED_STATUS } from "@/constants/auth";
import { THREAD_NOT_FOUND_STATUS } from "@/features/threads/constants/threads";
import { createThreadGuardHooks } from "@/features/threads/services/runtime-thread-guard";
import { createThreadOwnerStore } from "@/features/threads/services/thread-owners";
import type { ThreadOwnerStore } from "@/features/threads/types/threads";

vi.mock("@clerk/nextjs/server", () => ({ auth: vi.fn() }));

/** A runner that already holds runs for the thread `orphan`. */
const runtime = {
  runner: {
    ɵsupportsLocalThreadEndpoints: true,
    listThreads: () => [{ id: "orphan" }],
  },
} as never;

let currentUser: string | null;
let owners: ThreadOwnerStore;
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
      runtime,
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
  owners = createThreadOwnerStore();
  hooks = createThreadGuardHooks({
    getUserId: async () => currentUser,
    owners,
  });
});

describe("onBeforeHandler", () => {
  it("gives a new thread to the user who runs it first", async () => {
    expect(await statusFor(run, { threadId: "t1" })).toBeNull();
    expect(owners.getOwner("t1")).toBe("alice");
  });

  it("answers 404 to another user on every route about that thread", async () => {
    await statusFor(run, { threadId: "t1" });
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
    expect(owners.getOwner("t1")).toBe("alice");
  });

  it("lets the owner back into their thread", async () => {
    await statusFor(run, { threadId: "t1" });

    expect(await statusFor(connect, { threadId: "t1" })).toBeNull();
    expect(
      await statusFor({ method: "threads/messages", threadId: "t1" }),
    ).toBeNull();
  });

  it("refuses an unowned thread the runtime already holds, and does not claim it", async () => {
    expect(await statusFor(connect, { threadId: "orphan" })).toBe(
      THREAD_NOT_FOUND_STATUS,
    );
    expect(await statusFor(run, { threadId: "orphan" })).toBe(
      THREAD_NOT_FOUND_STATUS,
    );
    expect(owners.getOwner("orphan")).toBeUndefined();
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
});

describe("onResponse", () => {
  it("lists only the caller's threads", async () => {
    owners.claim("mine", "alice");
    owners.claim("theirs", "bob");
    const listed = Response.json({
      threads: [{ id: "mine" }, { id: "theirs" }, { id: "nobody" }],
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
      threads: [{ id: "mine" }],
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
