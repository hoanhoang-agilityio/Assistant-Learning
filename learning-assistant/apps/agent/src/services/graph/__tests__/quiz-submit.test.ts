import { type BaseEvent, EventType } from "@ag-ui/client";
import { MemorySaver } from "@langchain/langgraph";
import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import type { Quiz } from "@repo/shared/schemas";
import { v4 as uuidv4 } from "uuid";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { A2UI_ACTION_TOOL } from "../../../constants/graph";
import { TOOL_ERRORS } from "../../../constants/tools";
import { createChatModel } from "../../llm/chat-model";
import {
  createHandler,
  type Handler,
  lastMessages,
  lastSnapshot,
  readCheckpoint,
  runTurn,
  textOf,
  toolCallsOf,
  toolResultsOf,
  typesOf,
  userMessage,
} from "./runtime-harness";
import {
  EXPLANATIONS,
  isAfterTool,
  SECRET_EXPLANATION,
  teachThen,
} from "./scripted-agents";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

const SETTINGS = { questionCount: 3, learningLevel: "beginner", theme: "dark" };

/** The quiz's key is 1, 2, 3: two of these three are right. */
const ANSWERS = { q1: 1, q2: 0, q3: 3 };

let checkpointer: MemorySaver;
let handler: Handler;
let threadId: string;

const quizOf = (events: BaseEvent[]) => lastSnapshot(events).quiz as Quiz;

/** Research, learning material and a quiz, in one run. */
const reachQuiz = () =>
  runTurn(handler, {
    threadId,
    messages: [userMessage("teach me closures end to end")],
    forwardedProps: { settings: SETTINGS },
  });

/** The student answers on the canvas, then presses Submit. */
const submit = (
  previous: BaseEvent[],
  answers: Record<string, number>,
  quizId = quizOf(previous).id,
) =>
  runTurn(handler, {
    threadId,
    messages: lastMessages(previous),
    state: {
      ...lastSnapshot(previous),
      quiz: { ...quizOf(previous), answers },
    },
    forwardedProps: {
      settings: SETTINGS,
      a2uiAction: {
        userAction: {
          name: QUIZ_ACTIONS.submit,
          surfaceId: "quiz",
          context: { quizId, answers },
        },
      },
    },
  });

beforeEach(() => {
  vi.mocked(createChatModel).mockReset();
  vi.stubEnv("QUIZ_SEAL_SECRET", "test-secret");
  vi.stubEnv("TAVILY_API_KEY", "");
  checkpointer = new MemorySaver();
  handler = createHandler({ checkpointer });
  threadId = uuidv4();
});

describe("the Submit button", () => {
  it("grades the quiz in code, without the Supervisor's model", async () => {
    const { supervisorCalls } = teachThen();
    const quizzed = await reachQuiz();
    const callsBefore = supervisorCalls.length;

    const events = await submit(quizzed, ANSWERS);

    expect(toolCallsOf(events)).toEqual(["evaluate"]);
    expect(typesOf(events)).toContain(EventType.TOOL_CALL_ARGS);
    expect(typesOf(events).at(-1)).toBe(EventType.RUN_FINISHED);
    expect(supervisorCalls).toHaveLength(callsBefore);
    expect(textOf(events)).toBe("");
  });

  it("writes the grade, the score and the feedback, and reveals the answers", async () => {
    teachThen();
    const quizzed = await reachQuiz();

    const events = await submit(quizzed, ANSWERS);

    expect(lastSnapshot(events)).toMatchObject({
      stage: "evaluation",
      status: { running: null },
      draft: null,
      quiz: { answers: ANSWERS, submitted: true },
      evaluation: { correct: 2, total: 3, weakestConcept: "Closures" },
      score: { percent: 67, tier: "Practitioner" },
      feedback: { summary: EXPLANATIONS.summary },
    });
    const { evaluation, feedback } = lastSnapshot(events) as {
      evaluation: { perQuestion: object[] };
      feedback: { a2uiOperations: unknown[] };
    };
    expect(evaluation.perQuestion[0]).toMatchObject({
      qid: "q1",
      correctIndex: 1,
      isCorrect: true,
      explanation: "Explained 1.",
    });
    expect(feedback.a2uiOperations).toHaveLength(2);
    expect(toolResultsOf(events)).toEqual([
      {
        ok: true,
        data: {
          correct: 2,
          total: 3,
          weakestConcept: "Closures",
          score: { percent: 67, tier: "Practitioner" },
        },
      },
    ]);
  });

  it("keeps the grade when the Evaluator's own calls fail", async () => {
    teachThen(undefined, {
      explanations: new Error("No model."),
      feedback: new Error("No model."),
    });
    const quizzed = await reachQuiz();

    const events = await submit(quizzed, ANSWERS);

    const { evaluation } = lastSnapshot(events) as {
      evaluation: { correct: number; perQuestion: { explanation: string }[] };
    };
    expect(evaluation.correct).toBe(2);
    expect(evaluation.perQuestion[0]?.explanation).toBe(
      `${SECRET_EXPLANATION}-1`,
    );
  });

  it("leaves no trace of the button in the thread but the evaluate call", async () => {
    teachThen();
    const quizzed = await reachQuiz();

    const events = await submit(quizzed, ANSWERS);

    const thread = await readCheckpoint(checkpointer, threadId);
    expect(JSON.stringify(thread?.messages)).not.toContain(A2UI_ACTION_TOOL);
    expect(JSON.stringify(lastMessages(events))).not.toContain(
      A2UI_ACTION_TOOL,
    );
    expect(
      thread?.messages.slice(-3).map((message) => message.getType()),
    ).toEqual(["ai", "tool", "ai"]);
    expect(thread).toMatchObject({ pendingSubmit: false });
  });

  it("has the Supervisor explain a quiz that cannot be graded", async () => {
    const { supervisorCalls } = teachThen((messages) =>
      isAfterTool(messages)
        ? { text: "Answer every question first." }
        : { text: "Done." },
    );
    const quizzed = await reachQuiz();
    const callsBefore = supervisorCalls.length;

    const events = await submit(quizzed, { q1: 1 });

    expect(toolCallsOf(events)).toEqual(["evaluate"]);
    expect(lastSnapshot(events)).toMatchObject({
      stage: "quiz",
      evaluation: null,
      quiz: { submitted: false },
      status: { running: null, failed: "evaluate" },
    });
    expect(supervisorCalls).toHaveLength(callsBefore + 1);
    expect(textOf(events)).toBe("Answer every question first.");
  });

  it("refuses answers for a quiz that has been replaced", async () => {
    teachThen((messages) =>
      isAfterTool(messages)
        ? { text: "That quiz is gone." }
        : { text: "Done." },
    );
    const quizzed = await reachQuiz();

    const events = await submit(quizzed, ANSWERS, "an-older-quiz");

    expect(toolResultsOf(events)).toEqual([
      { ok: false, error: TOOL_ERRORS.staleQuiz },
    ]);
    expect(lastSnapshot(events)).toMatchObject({ evaluation: null });
  });

  it("refuses to grade the same quiz twice", async () => {
    teachThen((messages) =>
      isAfterTool(messages) ? { text: "Already graded." } : { text: "Done." },
    );
    const graded = await submit(await reachQuiz(), ANSWERS);

    const events = await runTurn(handler, {
      threadId,
      messages: lastMessages(graded),
      state: lastSnapshot(graded),
      forwardedProps: {
        settings: SETTINGS,
        a2uiAction: {
          userAction: {
            name: QUIZ_ACTIONS.submit,
            surfaceId: "quiz",
            context: { quizId: quizOf(graded).id, answers: ANSWERS },
          },
        },
      },
    });

    expect(toolResultsOf(events)).toEqual([
      { ok: false, error: TOOL_ERRORS.quizAlreadySubmitted },
    ]);
  });
});

describe("grading asked for in chat", () => {
  it("uses the answers the student picked on the canvas", async () => {
    teachThen((messages) =>
      isAfterTool(messages)
        ? { text: "Done." }
        : { toolCalls: [{ name: "evaluate", args: {} }] },
    );
    const quizzed = await reachQuiz();

    const events = await runTurn(handler, {
      threadId,
      messages: [...lastMessages(quizzed), userMessage("grade my answers")],
      state: {
        ...lastSnapshot(quizzed),
        quiz: { ...quizOf(quizzed), answers: ANSWERS },
      },
      forwardedProps: { settings: SETTINGS },
    });

    expect(lastSnapshot(events)).toMatchObject({
      stage: "evaluation",
      quiz: { answers: ANSWERS, submitted: true },
      evaluation: { correct: 2 },
    });
  });
});
