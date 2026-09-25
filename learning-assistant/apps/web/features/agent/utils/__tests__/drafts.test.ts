import { describe, expect, it } from "vitest";

import {
  toQuestionDrafts,
  toResearchDraft,
} from "@/features/agent/utils/drafts";

describe("toQuestionDrafts", () => {
  it("never carries the answer or the explanation", () => {
    const drafts = toQuestionDrafts({
      questions: [
        {
          concept: "Closures",
          question: "What does a closure capture?",
          options: ["Values", "Bindings"],
          correctIndex: 1,
          explanation: "Bindings.",
        },
      ],
    });

    expect(drafts).toEqual([
      {
        concept: "Closures",
        question: "What does a closure capture?",
        options: ["Values", "Bindings"],
      },
    ]);
  });

  it("skips a question whose text has not started", () => {
    expect(
      toQuestionDrafts({ questions: [{ concept: "Closures" }, undefined] }),
    ).toEqual([]);
  });
});

describe("toResearchDraft", () => {
  it("fills what is not written yet and keeps the sources", () => {
    const sources = [{ title: "MDN", url: "https://developer.mozilla.org" }];

    expect(
      toResearchDraft(
        {
          title: "Closures",
          keyTerms: [{ term: "Scope" }, { definition: "x" }],
        },
        sources,
      ),
    ).toEqual({
      title: "Closures",
      summary: "",
      keyInsight: "",
      keyTerms: [{ term: "Scope", definition: "" }],
      sources,
    });
  });
});
