import { describe, expect, it } from "vitest";

import {
  initialLearningState,
  LearningStateSchema,
  QuizDraftSchema,
  QuizSchema,
  SettingsSchema,
} from ".";

const draftQuestion = {
  concept: "Closures",
  question: "What does a closure capture?",
  options: ["Values", "Bindings", "Types", "Nothing"],
  correctIndex: 1,
  explanation: "Closures capture variable bindings, not copies of values.",
};

describe("LearningStateSchema", () => {
  it("accepts the initial state", () => {
    expect(LearningStateSchema.parse(initialLearningState)).toEqual(
      initialLearningState,
    );
  });

  it("rejects an unknown stage", () => {
    const bad = { ...initialLearningState, stage: "done" };
    expect(LearningStateSchema.safeParse(bad).success).toBe(false);
  });
});

describe("QuizSchema", () => {
  it("strips answer-key fields from questions", () => {
    const quiz = QuizSchema.parse({
      id: "q1",
      questions: [{ id: "a", ...draftQuestion }],
      answers: {},
      answerKeySealed: "sealed",
      submitted: false,
    });
    expect(quiz.questions[0]).not.toHaveProperty("correctIndex");
    expect(quiz.questions[0]).not.toHaveProperty("explanation");
  });

  it("rejects an answer outside the option range", () => {
    const result = QuizSchema.safeParse({
      id: "q1",
      questions: [],
      answers: { a: 4 },
      answerKeySealed: "sealed",
      submitted: false,
    });
    expect(result.success).toBe(false);
  });
});

describe("QuizDraftSchema", () => {
  it("accepts a question with exactly 4 options", () => {
    expect(
      QuizDraftSchema.safeParse({ questions: [draftQuestion] }).success,
    ).toBe(true);
  });

  it("rejects a question with 3 options", () => {
    const question = { ...draftQuestion, options: ["a", "b", "c"] };
    expect(QuizDraftSchema.safeParse({ questions: [question] }).success).toBe(
      false,
    );
  });
});

describe("SettingsSchema", () => {
  const settings = {
    questionCount: 5,
    learningLevel: "beginner",
    theme: "light",
  };

  it("accepts valid settings", () => {
    expect(SettingsSchema.safeParse(settings).success).toBe(true);
  });

  it.each([2, 21, 5.5])("rejects questionCount %s", (questionCount) => {
    expect(
      SettingsSchema.safeParse({ ...settings, questionCount }).success,
    ).toBe(false);
  });
});
