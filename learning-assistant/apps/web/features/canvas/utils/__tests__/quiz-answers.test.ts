import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import {
  initialLearningState,
  type LearningState,
  type Quiz,
} from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import {
  createSelectAnswerAction,
  parseSelectAnswer,
  retakeQuiz,
  selectAnswer,
} from "@/features/canvas/utils/quiz-answers";

const OPTIONS = ["a", "b", "c", "d"];

const QUIZ: Quiz = {
  id: "quiz-1",
  questions: [
    { id: "q1", concept: "A", question: "One?", options: OPTIONS },
    { id: "q2", concept: "B", question: "Two?", options: OPTIONS },
  ],
  answers: { q1: 0 },
  answerKeySealed: "sealed",
  submitted: false,
};

const withQuiz = (quiz: Partial<Quiz> = {}): LearningState => ({
  ...initialLearningState,
  stage: "quiz",
  quiz: { ...QUIZ, ...quiz },
});

describe("createSelectAnswerAction", () => {
  it("builds a select_answer event that parseSelectAnswer reads back", () => {
    const choice = { questionId: "q1", optionIndex: 2 };
    const action = createSelectAnswerAction(choice);

    expect(action.event.name).toBe(QUIZ_ACTIONS.selectAnswer);
    expect(parseSelectAnswer(action.event.context)).toEqual(choice);
  });
});

describe("parseSelectAnswer", () => {
  it("reads a valid choice", () => {
    expect(parseSelectAnswer({ questionId: "q1", optionIndex: 2 })).toEqual({
      questionId: "q1",
      optionIndex: 2,
    });
  });

  it.each([undefined, {}, { questionId: "q1", optionIndex: 4 }])(
    "rejects %j",
    (context) => {
      expect(parseSelectAnswer(context)).toBeNull();
    },
  );
});

describe("selectAnswer", () => {
  it("records the choice and keeps the others", () => {
    const next = selectAnswer(withQuiz(), { questionId: "q2", optionIndex: 3 });
    expect(next.quiz?.answers).toEqual({ q1: 0, q2: 3 });
  });

  it("changes an earlier choice", () => {
    const next = selectAnswer(withQuiz(), { questionId: "q1", optionIndex: 1 });
    expect(next.quiz?.answers).toEqual({ q1: 1 });
  });

  it.each<[string, LearningState, string, number]>([
    ["no quiz", initialLearningState, "q1", 1],
    ["a graded quiz", withQuiz({ submitted: true }), "q1", 1],
    ["an unknown question", withQuiz(), "q9", 1],
    ["the same option", withQuiz(), "q1", 0],
  ])("returns the same state for %s", (_, state, questionId, optionIndex) => {
    expect(selectAnswer(state, { questionId, optionIndex })).toBe(state);
  });
});

describe("retakeQuiz", () => {
  it("clears the answers and the results, keeps the questions", () => {
    const graded: LearningState = {
      ...withQuiz({ answers: { q1: 0, q2: 1 }, submitted: true }),
      stage: "evaluation",
      score: { percent: 50, tier: "Practitioner" },
      feedback: { a2uiOperations: [], summary: "Ok." },
    };
    const next = retakeQuiz(graded);

    expect(next.quiz).toEqual({ ...QUIZ, answers: {}, submitted: false });
    expect(next).toMatchObject({
      stage: "quiz",
      evaluation: null,
      score: null,
      feedback: null,
      reflection: null,
    });
  });

  it("returns the same state without a quiz", () => {
    expect(retakeQuiz(initialLearningState)).toBe(initialLearningState);
  });
});
