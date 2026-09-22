import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import {
  initialLearningState,
  type LearningState,
  type Quiz,
} from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { RETRY_MESSAGES } from "@/features/canvas/constants/retry";
import { getRetryAction } from "@/features/canvas/utils/retry";

const quiz: Quiz = {
  id: "q1",
  questions: [],
  answers: { a: 1 },
  answerKeySealed: "sealed",
  submitted: false,
};

const withFailure = (
  failed: LearningState["status"]["failed"],
  extra: Partial<LearningState> = {},
): LearningState => ({
  ...initialLearningState,
  ...extra,
  status: { running: null, error: "boom", failed },
});

describe("getRetryAction", () => {
  it("returns null when nothing failed", () => {
    expect(getRetryAction(initialLearningState)).toBeNull();
  });

  it.each(["research", "notes", "simplify", "quiz"] as const)(
    "asks the assistant again when %s failed",
    (failed) => {
      expect(getRetryAction(withFailure(failed))).toEqual({
        kind: "message",
        content: RETRY_MESSAGES[failed],
      });
    },
  );

  it("submits the quiz again when grading failed", () => {
    const action = getRetryAction(withFailure("evaluate", { quiz }));
    expect(action).toEqual({
      kind: "submit",
      action: {
        userAction: expect.objectContaining({
          name: QUIZ_ACTIONS.submit,
          context: { quizId: "q1", answers: { a: 1 } },
        }),
      },
    });
  });

  it("cannot retry grading without an unsubmitted quiz", () => {
    expect(getRetryAction(withFailure("evaluate"))).toBeNull();
    expect(
      getRetryAction(
        withFailure("evaluate", { quiz: { ...quiz, submitted: true } }),
      ),
    ).toBeNull();
  });
});
