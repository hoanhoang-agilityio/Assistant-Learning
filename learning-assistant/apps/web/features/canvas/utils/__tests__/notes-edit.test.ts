import { initialLearningState, type LearningState } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import {
  applyNotesEdit,
  setNotesView,
} from "@/features/canvas/utils/notes-edit";

const withNotes: LearningState = {
  ...initialLearningState,
  stage: "notes",
  notes: { original: "# Notes", simplified: null, view: "original" },
};

const withResults: LearningState = {
  ...withNotes,
  stage: "score",
  quiz: {
    id: "q1",
    questions: [],
    answers: {},
    answerKeySealed: "sealed",
    submitted: true,
  },
  evaluation: {
    correct: 1,
    total: 1,
    percent: 100,
    weakestConcept: null,
    perQuestion: [],
    mastery: [],
  },
  score: { percent: 100, tier: "Master" },
  feedback: { a2uiOperations: [], summary: "Great" },
  reflection: { rating: 5, text: "Fun" },
};

describe("applyNotesEdit", () => {
  it("writes the original notes when that view is active", () => {
    const next = applyNotesEdit(withNotes, "# Edited");
    expect(next.notes).toEqual({ ...withNotes.notes, original: "# Edited" });
  });

  it("writes the simplified notes when that view is active", () => {
    const state: LearningState = {
      ...withNotes,
      notes: { original: "# Notes", simplified: "# Easy", view: "simplified" },
    };
    const next = applyNotesEdit(state, "# Easier");
    expect(next.notes).toEqual({
      original: "# Notes",
      simplified: "# Easier",
      view: "simplified",
    });
  });

  it("clears the quiz and everything built from it", () => {
    const next = applyNotesEdit(withResults, "# Edited");
    expect(next).toMatchObject({
      quiz: null,
      evaluation: null,
      score: null,
      feedback: null,
      reflection: null,
      quizOutdated: true,
    });
  });

  it("moves a later stage back to notes", () => {
    expect(applyNotesEdit(withResults, "# Edited").stage).toBe("notes");
  });

  it("does not flag the quiz as outdated when there was none", () => {
    const next = applyNotesEdit(withNotes, "# Edited");
    expect(next.quizOutdated).toBe(false);
    expect(next.stage).toBe("notes");
  });

  it("keeps the outdated flag set on later edits", () => {
    const once = applyNotesEdit(withResults, "# Edited");
    expect(applyNotesEdit(once, "# Edited again").quizOutdated).toBe(true);
  });

  it("returns the same state when the text did not change", () => {
    expect(applyNotesEdit(withResults, "# Notes")).toBe(withResults);
  });

  it("returns the same state when there are no notes", () => {
    expect(applyNotesEdit(initialLearningState, "x")).toBe(
      initialLearningState,
    );
  });
});

describe("setNotesView", () => {
  it("switches the view and keeps the quiz", () => {
    const next = setNotesView(withResults, "simplified");
    expect(next.notes?.view).toBe("simplified");
    expect(next.quiz).toBe(withResults.quiz);
  });
});
