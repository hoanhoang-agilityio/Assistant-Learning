import { describe, expect, it } from "vitest";

import { getQuizActionAvailability } from "@/features/canvas/utils/quiz-actions";

const OPEN = {
  answeredCount: 0,
  canSubmit: false,
  isSubmitted: false,
  isLocked: false,
};

describe("getQuizActionAvailability", () => {
  it("allows only New questions on an untouched quiz", () => {
    expect(getQuizActionAvailability(OPEN)).toEqual({
      canSubmit: false,
      canRetake: false,
      canAskNew: true,
    });
  });

  it("allows Submit and Retake on a fully answered quiz", () => {
    expect(
      getQuizActionAvailability({ ...OPEN, answeredCount: 3, canSubmit: true }),
    ).toEqual({ canSubmit: true, canRetake: true, canAskNew: true });
  });

  it("allows Retake but not Submit after grading", () => {
    expect(
      getQuizActionAvailability({
        ...OPEN,
        answeredCount: 3,
        canSubmit: true,
        isSubmitted: true,
      }),
    ).toEqual({ canSubmit: false, canRetake: true, canAskNew: true });
  });

  it("allows nothing while the agent runs", () => {
    expect(
      getQuizActionAvailability({
        ...OPEN,
        answeredCount: 3,
        canSubmit: true,
        isLocked: true,
      }),
    ).toEqual({ canSubmit: false, canRetake: false, canAskNew: false });
  });
});
