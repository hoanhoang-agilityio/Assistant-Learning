import { EMPTY_PROFILE } from "@repo/shared/constants/memory";
import type { StudentMemory } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import {
  clearProfileFormField,
  createProfileUpdate,
  isSameMemoryItem,
  isWeakConcept,
  removeMemoryItem,
  toProfileFormValues,
} from "@/features/memory/utils/memory";

const PROFILE = {
  level: "beginner",
  style: "Analogies",
  language: null,
} as const;
const UPDATED_AT = "2026-10-01T10:00:00.000Z";
const TOPIC_ID = "8c3c5d0e-4f43-4c39-9a51-6f1f0a2b9c11";

const MEMORY: StudentMemory = {
  profile: PROFILE,
  concepts: [
    {
      key: "scope",
      concept: "Scope",
      correct: 1,
      total: 4,
      percent: 25,
      updatedAt: UPDATED_AT,
    },
    {
      key: "closures",
      concept: "Closures",
      correct: 3,
      total: 3,
      percent: 100,
      updatedAt: UPDATED_AT,
    },
  ],
  topics: [
    {
      conversationId: TOPIC_ID,
      topic: "Closures",
      bestPercent: 80,
      latestPercent: 60,
      attempts: 2,
      updatedAt: UPDATED_AT,
    },
  ],
};

describe("toProfileFormValues", () => {
  it("shows an unset text field as empty", () => {
    expect(toProfileFormValues(PROFILE)).toEqual({
      level: "beginner",
      style: "Analogies",
      language: "",
    });
  });
});

describe("createProfileUpdate", () => {
  it("is null when nothing changed, ignoring spaces around the text", () => {
    expect(
      createProfileUpdate(PROFILE, {
        level: "beginner",
        style: " Analogies ",
        language: "  ",
      }),
    ).toBeNull();
  });

  it("sends only the changed fields, trimmed", () => {
    expect(
      createProfileUpdate(PROFILE, {
        level: "advanced",
        style: "Analogies",
        language: " Vietnamese ",
      }),
    ).toEqual({ level: "advanced", language: "Vietnamese" });
  });

  it("forgets a cleared field or level with null", () => {
    expect(
      createProfileUpdate(PROFILE, { level: null, style: "", language: "" }),
    ).toEqual({ level: null, style: null });
  });

  it("sets fields on an empty profile", () => {
    expect(
      createProfileUpdate(EMPTY_PROFILE, {
        level: null,
        style: "Short",
        language: "",
      }),
    ).toEqual({ style: "Short" });
  });
});

describe("removeMemoryItem", () => {
  it("drops one concept by its key", () => {
    expect(
      removeMemoryItem(MEMORY, { kind: "concepts", id: "scope" }).concepts.map(
        ({ key }) => key,
      ),
    ).toEqual(["closures"]);
  });

  it("drops one topic by its conversation", () => {
    expect(
      removeMemoryItem(MEMORY, { kind: "topics", id: TOPIC_ID }).topics,
    ).toEqual([]);
  });

  it("clears one profile field and nothing else", () => {
    expect(
      removeMemoryItem(MEMORY, { kind: "profile", id: "style" }).profile,
    ).toEqual({
      ...PROFILE,
      style: null,
    });
  });

  it("changes nothing for a field that does not exist", () => {
    expect(removeMemoryItem(MEMORY, { kind: "profile", id: "age" })).toBe(
      MEMORY,
    );
  });
});

describe("clearProfileFormField", () => {
  const VALUES = {
    level: "advanced",
    style: "Edited",
    language: "French",
  } as const;

  it("unsets the forgotten field and keeps the others as edited", () => {
    expect(clearProfileFormField(VALUES, "level")).toEqual({
      ...VALUES,
      level: null,
    });
    expect(clearProfileFormField(VALUES, "language")).toEqual({
      ...VALUES,
      language: "",
    });
  });

  it("changes nothing for a field that does not exist", () => {
    expect(clearProfileFormField(VALUES, "age")).toBe(VALUES);
  });
});

describe("isSameMemoryItem", () => {
  it("matches kind and id", () => {
    expect(
      isSameMemoryItem(
        { kind: "concepts", id: "scope" },
        { kind: "concepts", id: "scope" },
      ),
    ).toBe(true);
    expect(
      isSameMemoryItem(
        { kind: "topics", id: "scope" },
        { kind: "concepts", id: "scope" },
      ),
    ).toBe(false);
    expect(isSameMemoryItem(null, { kind: "concepts", id: "scope" })).toBe(
      false,
    );
  });
});

describe("isWeakConcept", () => {
  it("is weak under 70%", () => {
    expect(MEMORY.concepts.map(isWeakConcept)).toEqual([true, false]);
  });
});
