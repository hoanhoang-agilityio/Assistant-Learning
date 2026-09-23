import { beforeEach, describe, expect, it, vi } from "vitest";

import { TEST_RUN_SETTINGS } from "@/features/agent/services/__tests__/quiz-fixtures";
import {
  QUIZ_DRAFT,
  SECRET_EXPLANATION,
} from "@/features/agent/services/__tests__/quiz-fixtures";
import { createSealedQuiz } from "@/features/agent/services/answer-key/seal-quiz";
import { SealedAnswerKeyStore } from "@/features/agent/services/answer-key/sealed-answer-key-store";
import { runEvaluation } from "@/features/agent/services/evaluate";
import { runEvaluator } from "@/features/agent/services/subagents/evaluator";
import { runFeedbackSurface } from "@/features/agent/services/subagents/feedback-surface";

vi.mock("@/features/agent/services/subagents/evaluator", () => ({
  runEvaluator: vi.fn(),
}));

vi.mock("@/features/agent/services/subagents/feedback-surface", () => ({
  runFeedbackSurface: vi.fn(),
}));

const OPERATIONS = [
  { version: "v0.9", createSurface: { surfaceId: "feedback" } },
];

const setup = async () => {
  const answerKeys = new SealedAnswerKeyStore("test-secret");
  const quiz = await createSealedQuiz(QUIZ_DRAFT, answerKeys);
  const [q1, q2, q3] = quiz.questions.map(({ id }) => id);
  if (!q1 || !q2 || !q3) {
    throw new Error("The quiz has too few questions.");
  }
  // Correct answers are 1, 2, 3: two right, one wrong (Scope).
  const answers = { [q1]: 1, [q2]: 2, [q3]: 0 };
  return {
    quiz,
    ids: [q1, q2, q3],
    params: {
      quiz,
      answers,
      answerKeys,
      material: "# Closures",
      settings: TEST_RUN_SETTINGS,
    },
  };
};

describe("runEvaluation", () => {
  beforeEach(() => {
    vi.mocked(runEvaluator).mockReset();
    vi.mocked(runFeedbackSurface).mockReset();
  });

  it("grades in code and adds the Evaluator's explanations, summary and surface", async () => {
    const { ids, params } = await setup();
    vi.mocked(runEvaluator).mockResolvedValue({
      explanations: [{ qid: ids[2] ?? "", explanation: "Scope is lexical." }],
      summary: "Great work on closures.",
    });
    vi.mocked(runFeedbackSurface).mockResolvedValue(OPERATIONS);

    const result = await runEvaluation(params);

    expect(result.evaluation).toMatchObject({
      correct: 2,
      total: 3,
      percent: 67,
      weakestConcept: "Scope",
      mastery: [
        { concept: "Closures", percent: 100 },
        { concept: "Scope", percent: 0 },
      ],
    });
    expect(result.evaluation.perQuestion.map((q) => q.explanation)).toEqual([
      `${SECRET_EXPLANATION}-1`,
      `${SECRET_EXPLANATION}-2`,
      "Scope is lexical.",
    ]);
    expect(result.score).toEqual({ percent: 67, tier: "Practitioner" });
    expect(result.feedback).toEqual({
      a2uiOperations: OPERATIONS,
      summary: "Great work on closures.",
    });

    const [call] = vi.mocked(runEvaluator).mock.calls[0] ?? [];
    expect(call?.input.material).toBe("# Closures");
    expect(call?.input.questions[2]).toMatchObject({
      chosenIndex: 0,
      correctIndex: 3,
      isCorrect: false,
    });
  });

  it("keeps the grade when both Evaluator calls fail", async () => {
    const { params } = await setup();
    vi.mocked(runEvaluator).mockRejectedValue(new Error("rate limited"));
    vi.mocked(runFeedbackSurface).mockRejectedValue(new Error("invalid"));
    vi.spyOn(console, "warn").mockImplementation(() => {});

    const result = await runEvaluation(params);

    expect(result.score.tier).toBe("Practitioner");
    expect(result.evaluation.perQuestion[2]?.explanation).toBe(
      `${SECRET_EXPLANATION}-3`,
    );
    expect(result.feedback.a2uiOperations).toEqual([]);
    expect(result.feedback.summary).toContain("2 of 3");
    expect(result.feedback.summary).toContain('"Scope"');
  });

  it("stops instead of falling back when the run is aborted", async () => {
    const { params } = await setup();
    const controller = new AbortController();
    controller.abort();
    vi.mocked(runEvaluator).mockRejectedValue(new Error("aborted"));
    vi.mocked(runFeedbackSurface).mockResolvedValue([]);

    await expect(
      runEvaluation({ ...params, signal: controller.signal }),
    ).rejects.toThrow("aborted");
  });
});
