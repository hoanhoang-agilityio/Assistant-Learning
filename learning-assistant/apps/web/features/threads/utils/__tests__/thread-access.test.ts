import { describe, expect, it } from "vitest";

import type { RuntimeRouteMethod } from "@/features/threads/types/threads";
import { getThreadAccess } from "@/features/threads/utils/thread-access";

const access = (
  method: RuntimeRouteMethod,
  ownerId: string | undefined,
  threadId: string | undefined = "t1",
  hasRuns = false,
) => getThreadAccess({ method, threadId, ownerId, userId: "me", hasRuns });

describe("getThreadAccess", () => {
  it.each<RuntimeRouteMethod>(["agent/run", "agent/suggest"])(
    "%s claims a new thread, continues its own, is denied another's",
    (method) => {
      expect(access(method, undefined)).toBe("claim");
      expect(access(method, "me")).toBe("allow");
      expect(access(method, "other")).toBe("deny");
    },
  );

  it("agent/connect opens its own or a new thread, not another's", () => {
    expect(access("agent/connect", undefined)).toBe("allow");
    expect(access("agent/connect", "me")).toBe("allow");
    expect(access("agent/connect", "other")).toBe("deny");
  });

  it.each<RuntimeRouteMethod>([
    "agent/stop",
    "threads/messages",
    "threads/events",
    "threads/state",
    "threads/archive",
    "threads/update",
  ])("%s is for the owner only, even of an unowned thread", (method) => {
    expect(access(method, "me")).toBe("allow");
    expect(access(method, "other")).toBe("deny");
    expect(access(method, undefined)).toBe("deny");
  });

  it.each<RuntimeRouteMethod>(["threads/clear", "threads/subscribe"])(
    "%s is never allowed",
    (method) => {
      expect(access(method, undefined, undefined)).toBe("deny");
      expect(access(method, "me")).toBe("deny");
    },
  );

  it.each<RuntimeRouteMethod>([
    "agent/run",
    "agent/suggest",
    "agent/connect",
    "threads/messages",
  ])("%s is denied on an unowned thread that already has runs", (method) => {
    expect(access(method, undefined, "t1", true)).toBe("deny");
  });

  it.each<RuntimeRouteMethod>(["info", "threads/list"])(
    "%s names no thread and is allowed",
    (method) => {
      expect(access(method, undefined, undefined)).toBe("allow");
    },
  );
});
