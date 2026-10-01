import { describe, expect, it } from "vitest";

import type { RuntimeRouteMethod } from "@/features/conversations/types/threads";
import { getThreadAccess } from "@/features/conversations/utils/thread-access";

const access = (
  method: RuntimeRouteMethod,
  threadId: string | undefined,
  ownerId: string | undefined,
) => getThreadAccess({ method, threadId, ownerId, userId: "alice" });

describe("getThreadAccess", () => {
  it.each([
    "agent/run",
    "agent/connect",
    "agent/stop",
    "threads/messages",
  ] as const)("lets the owner use %s", (method) => {
    expect(access(method, "t1", "alice")).toBe("allow");
  });

  it.each([
    "agent/run",
    "agent/connect",
    "agent/stop",
    "threads/state",
  ] as const)("denies %s on another user's thread", (method) => {
    expect(access(method, "t1", "bob")).toBe("deny");
  });

  it.each(["agent/run", "agent/connect"] as const)(
    "denies %s on a thread no conversation has",
    (method) => {
      expect(access(method, "t1", undefined)).toBe("deny");
    },
  );

  it("allows routes about no thread", () => {
    expect(access("info", undefined, undefined)).toBe("allow");
    expect(access("threads/list", undefined, undefined)).toBe("allow");
  });

  it.each(["threads/clear", "threads/subscribe"] as const)(
    "never allows %s",
    (method) => {
      expect(access(method, undefined, undefined)).toBe("deny");
    },
  );
});
