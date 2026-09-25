import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import { describe, expect, it } from "vitest";

import { parseSubmitAction } from "../submit-action";

const createForwardedProps = (name: string, context?: unknown) => ({
  settings: {},
  a2uiAction: { userAction: { name, surfaceId: "quiz", context } },
});

describe("parseSubmitAction", () => {
  it("is null for a run without an action", () => {
    expect(parseSubmitAction({ settings: {} })).toBeNull();
    expect(parseSubmitAction(undefined)).toBeNull();
  });

  it("is null for another action", () => {
    expect(
      parseSubmitAction(createForwardedProps(QUIZ_ACTIONS.retake)),
    ).toBeNull();
  });

  it("reads the quiz id and answers from a Submit", () => {
    const submission = { quizId: "quiz-1", answers: { q1: 2 } };
    expect(
      parseSubmitAction(createForwardedProps(QUIZ_ACTIONS.submit, submission)),
    ).toEqual({ submission });
  });

  it("still counts a Submit whose context is invalid", () => {
    expect(
      parseSubmitAction(
        createForwardedProps(QUIZ_ACTIONS.submit, { answers: { q1: 9 } }),
      ),
    ).toEqual({});
  });
});
