import { describe, expect, it } from "vitest";

import {
  ABANDONED_AFTER_MS,
  AUTO_TITLE_MAX_LENGTH,
} from "../../constants/conversations";
import {
  createAutoTitle,
  getConversationStatus,
  getStoredStatus,
} from "../conversations";

describe("getStoredStatus", () => {
  it.each([
    ["idle", "active"],
    ["research", "active"],
    ["quiz", "active"],
    ["evaluation", "completed"],
    ["feedback", "completed"],
  ] as const)("%s is %s", (stage, status) => {
    expect(getStoredStatus(stage)).toBe(status);
  });
});

describe("getConversationStatus", () => {
  const now = new Date("2026-10-01T12:00:00Z");
  const ago = (ms: number) => new Date(now.getTime() - ms);

  it("keeps an active conversation active within a week", () => {
    expect(getConversationStatus("active", ago(ABANDONED_AFTER_MS), now)).toBe(
      "active",
    );
  });

  it("reads an active conversation idle for over a week as abandoned", () => {
    expect(
      getConversationStatus("active", ago(ABANDONED_AFTER_MS + 1), now),
    ).toBe("abandoned");
  });

  it("never abandons a completed conversation", () => {
    expect(
      getConversationStatus("completed", ago(ABANDONED_AFTER_MS * 4), now),
    ).toBe("completed");
  });
});

describe("createAutoTitle", () => {
  it("keeps a short message on one line", () => {
    expect(createAutoTitle("  Teach me\n closures  ")).toBe(
      "Teach me closures",
    );
  });

  it("is null for a message with no text", () => {
    expect(createAutoTitle(" \n ")).toBeNull();
  });

  it("cuts a long message at a word and marks the cut", () => {
    const title = createAutoTitle(
      "Explain how the JavaScript event loop schedules microtasks and macrotasks in detail",
    );
    expect(title).toBe(
      "Explain how the JavaScript event loop schedules microtasks…",
    );
    expect(title!.length).toBeLessThanOrEqual(AUTO_TITLE_MAX_LENGTH);
  });

  it("cuts a long word where it must", () => {
    const title = createAutoTitle("x".repeat(100));
    expect(title).toHaveLength(AUTO_TITLE_MAX_LENGTH);
  });
});
