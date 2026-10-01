import {
  type ConversationSummary,
  initialLearningState,
  type Quiz,
} from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { UNTITLED_TITLE } from "@/features/conversations/constants/conversations";
import {
  filterConversations,
  formatResumeMessage,
  formatScore,
  getConversationTitle,
  pickConversation,
  pickNextConversation,
  toActiveConversation,
} from "@/features/conversations/utils/conversations";

const conversation = (
  id: string,
  overrides: Partial<ConversationSummary> = {},
): ConversationSummary => ({
  id,
  title: `Title ${id}`,
  topic: null,
  stage: "idle",
  status: "active",
  score: null,
  lastActivityAt: "2026-10-01T00:00:00.000Z",
  createdAt: "2026-10-01T00:00:00.000Z",
  ...overrides,
});

const QUIZ: Quiz = {
  id: "quiz_1",
  questions: [1, 2, 3, 4, 5].map((n) => ({
    id: `q${n}`,
    concept: "Scope",
    question: `Q${n}?`,
    options: ["a", "b"],
  })),
  answers: { q1: 0, q2: 1, q3: 0 },
  answerKeySealed: "sealed",
  submitted: false,
};

describe("getConversationTitle", () => {
  it("names an untitled conversation for what it is", () => {
    expect(getConversationTitle(conversation("a", { title: null }))).toBe(
      UNTITLED_TITLE,
    );
  });
});

describe("filterConversations", () => {
  const list = [
    conversation("a", { title: "Closures", topic: "javascript closures" }),
    conversation("b", { title: "Black holes", topic: "astrophysics" }),
  ];

  it("matches the title or the topic, ignoring case", () => {
    expect(filterConversations(list, "CLOSURE").map(({ id }) => id)).toEqual([
      "a",
    ]);
    expect(filterConversations(list, "astro").map(({ id }) => id)).toEqual([
      "b",
    ]);
  });

  it("keeps every conversation for an empty query", () => {
    expect(filterConversations(list, "  ")).toBe(list);
  });
});

describe("pickConversation", () => {
  const list = [conversation("recent"), conversation("older")];

  it("reopens the conversation open last time", () => {
    expect(pickConversation(list, "older")?.id).toBe("older");
  });

  it("falls back to the most recent one when the saved one is gone", () => {
    expect(pickConversation(list, "deleted")?.id).toBe("recent");
    expect(pickConversation(list, undefined)?.id).toBe("recent");
  });

  it("is null without conversations", () => {
    expect(pickConversation([], "x")).toBeNull();
  });
});

describe("pickNextConversation", () => {
  it("is the most recent other conversation", () => {
    const list = [conversation("a"), conversation("b")];

    expect(pickNextConversation(list, "a")?.id).toBe("b");
    expect(pickNextConversation(list, "b")?.id).toBe("a");
    expect(pickNextConversation([conversation("a")], "a")).toBeNull();
  });
});

describe("toActiveConversation", () => {
  it("opens an untitled conversation as new", () => {
    expect(toActiveConversation(conversation("a", { title: null }))).toEqual({
      id: "a",
      isNew: true,
    });
    expect(toActiveConversation(conversation("b"))).toEqual({
      id: "b",
      isNew: false,
    });
  });
});

describe("formatResumeMessage", () => {
  it("says how far the quiz got", () => {
    expect(
      formatResumeMessage({
        ...initialLearningState,
        stage: "quiz",
        quiz: QUIZ,
      }),
    ).toBe("You were on the Quiz stage, 3/5 answered.");
  });

  it("names the stage otherwise", () => {
    expect(
      formatResumeMessage({ ...initialLearningState, stage: "material" }),
    ).toBe("You were on the Learning Material stage.");
  });

  it("is null for a conversation that has not started", () => {
    expect(formatResumeMessage(initialLearningState)).toBeNull();
  });
});

describe("formatScore", () => {
  it("shows the percent and the tier", () => {
    expect(formatScore({ percent: 66.7, tier: "Practitioner" })).toBe(
      "67% · Practitioner",
    );
  });
});
