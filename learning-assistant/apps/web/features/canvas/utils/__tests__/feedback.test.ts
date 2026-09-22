import {
  FEEDBACK_ACTIONS,
  FEEDBACK_SURFACE_ID,
} from "@repo/shared/a2ui/feedback-catalog";
import { describe, expect, it } from "vitest";

import {
  createReviewConceptAction,
  formatReflectionMessage,
  parseFeedbackOperations,
  parseReviewConcept,
  toReflection,
} from "@/features/canvas/utils/feedback";

const CREATE = {
  version: "v0.9",
  createSurface: { surfaceId: FEEDBACK_SURFACE_ID, catalogId: "c" },
};
const COMPONENTS = {
  version: "v0.9",
  updateComponents: { surfaceId: FEEDBACK_SURFACE_ID, components: [] },
};

describe("parseFeedbackOperations", () => {
  it("keeps operations that create and fill the Feedback surface", () => {
    expect(parseFeedbackOperations([CREATE, COMPONENTS])).toEqual([
      CREATE,
      COMPONENTS,
    ]);
  });

  it.each([
    ["no operations", []],
    ["no createSurface first", [COMPONENTS, CREATE]],
    [
      "another surface",
      [CREATE, { ...COMPONENTS, updateComponents: { surfaceId: "x" } }],
    ],
    ["another version", [{ ...CREATE, version: "v0.8" }]],
    ["two kinds in one operation", [{ ...CREATE, ...COMPONENTS }]],
    ["a non-object", [CREATE, "oops"]],
  ])("is empty for %s", (_case, operations) => {
    expect(parseFeedbackOperations(operations)).toEqual([]);
  });
});

describe("review concept action", () => {
  it("round-trips the concept", () => {
    const { event } = createReviewConceptAction("Scope");
    expect(event.name).toBe(FEEDBACK_ACTIONS.reviewConcept);
    expect(parseReviewConcept(event.context)).toBe("Scope");
  });

  it("rejects a context without a concept", () => {
    expect(parseReviewConcept({})).toBeNull();
    expect(parseReviewConcept(null)).toBeNull();
  });
});

describe("toReflection", () => {
  it("trims the text", () => {
    expect(toReflection({ rating: 4, text: "  more examples " })).toEqual({
      rating: 4,
      text: "more examples",
    });
  });

  it.each([0, 6, 2.5])("rejects a rating of %s", (rating) => {
    expect(toReflection({ rating, text: "" })).toBeNull();
  });
});

describe("formatReflectionMessage", () => {
  it("includes the rating and the text", () => {
    expect(formatReflectionMessage({ rating: 4, text: "More examples" })).toBe(
      "My reflection (4/5): More examples",
    );
  });

  it("still says something without text", () => {
    expect(formatReflectionMessage({ rating: 2, text: "" })).toBe(
      "My reflection: I rated this lesson 2/5.",
    );
  });
});
