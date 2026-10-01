import type { BaseEvent } from "@ag-ui/client";
import { MemorySaver } from "@langchain/langgraph";
import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import type { Quiz } from "@repo/shared/schemas";
import { v4 as uuidv4 } from "uuid";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { LearningRecords } from "../../../types/records";
import { createChatModel } from "../../llm/chat-model";
import { createMemoryRecords, type RecordedCall } from "./memory-records";
import {
  createHandler,
  lastMessages,
  lastSnapshot,
  runTurn,
  toolResultsOf,
  userMessage,
} from "./runtime-harness";
import { MATERIAL, RESEARCH, teachThen } from "./scripted-agents";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

const SETTINGS = { questionCount: 3, learningLevel: "beginner", theme: "dark" };
const TEACH = "teach me closures end to end";

let threadId: string;

const quizOf = (events: BaseEvent[]) => lastSnapshot(events).quiz as Quiz;

const methodsOf = (calls: RecordedCall[]) => calls.map(({ method }) => method);

const callOf = (calls: RecordedCall[], method: keyof LearningRecords) =>
  calls.find((call) => call.method === method);

const setUp = (records?: LearningRecords) => {
  const memory = createMemoryRecords();
  const handler = createHandler({
    checkpointer: new MemorySaver(),
    records: records ?? memory.records,
  });
  return { handler, calls: memory.calls };
};

beforeEach(() => {
  vi.mocked(createChatModel).mockReset();
  vi.stubEnv("QUIZ_SEAL_SECRET", "test-secret");
  vi.stubEnv("TAVILY_API_KEY", "");
  threadId = uuidv4();
});

describe("conversation records", () => {
  it("keeps each stage from the tool's own result as it completes", async () => {
    teachThen();
    const { handler, calls } = setUp();

    const events = await runTurn(handler, {
      threadId,
      messages: [userMessage(TEACH)],
      forwardedProps: { settings: SETTINGS },
    });

    expect(methodsOf(calls)).toEqual([
      "recordResearch",
      "recordMaterial",
      "recordQuiz",
      "recordRun",
    ]);
    expect(calls.every((call) => call.threadId === threadId)).toBe(true);
    expect(callOf(calls, "recordResearch")?.value).toMatchObject({
      topic: "closures",
      research: { title: RESEARCH.title },
    });
    expect(callOf(calls, "recordMaterial")?.value).toEqual({
      original: MATERIAL.markdown,
      simplified: null,
      view: "original",
    });
    expect(callOf(calls, "recordQuiz")?.value).toEqual(quizOf(events));
    expect(callOf(calls, "recordRun")?.value).toEqual({
      stage: "quiz",
      userText: TEACH,
    });
  });

  it("keeps the graded quiz and notes a Submit run without a message", async () => {
    teachThen();
    const { handler, calls } = setUp();
    const quizzed = await runTurn(handler, {
      threadId,
      messages: [userMessage(TEACH)],
      forwardedProps: { settings: SETTINGS },
    });
    const answers = { q1: 1, q2: 0, q3: 3 };
    calls.length = 0;

    await runTurn(handler, {
      threadId,
      messages: lastMessages(quizzed),
      state: {
        ...lastSnapshot(quizzed),
        quiz: { ...quizOf(quizzed), answers },
      },
      forwardedProps: {
        settings: SETTINGS,
        a2uiAction: {
          userAction: {
            name: QUIZ_ACTIONS.submit,
            surfaceId: "quiz",
            context: { quizId: quizOf(quizzed).id, answers },
          },
        },
      },
    });

    expect(methodsOf(calls)).toEqual(["recordEvaluation", "recordRun"]);
    expect(callOf(calls, "recordEvaluation")?.value).toMatchObject({
      quiz: { id: quizOf(quizzed).id, answers, submitted: true },
      score: { percent: 67, tier: "Practitioner" },
      evaluation: { correct: 2, total: 3 },
    });
    expect(callOf(calls, "recordRun")?.value).toEqual({
      stage: "evaluation",
      userText: null,
    });
  });

  it("keeps nothing for a stage that failed, but still notes the run", async () => {
    teachThen(undefined, { research: new Error("model down") });
    const { handler, calls } = setUp();

    await runTurn(handler, {
      threadId,
      messages: [userMessage(TEACH)],
      forwardedProps: { settings: SETTINGS },
    });

    expect(methodsOf(calls)).toEqual(["recordRun"]);
    expect(callOf(calls, "recordRun")?.value).toEqual({
      stage: "idle",
      userText: TEACH,
    });
  });

  it("completes a stage even when keeping it fails", async () => {
    teachThen(() => ({ text: "Done." }));
    const failing = createMemoryRecords().records;
    failing.recordResearch = async () => {
      throw new Error("database down");
    };
    const { handler } = setUp(failing);
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});

    const events = await runTurn(handler, {
      threadId,
      messages: [userMessage(TEACH)],
      forwardedProps: { settings: SETTINGS },
    });

    expect(lastSnapshot(events)).toMatchObject({
      research: { title: RESEARCH.title },
    });
    expect(toolResultsOf(events)[0]).toMatchObject({ ok: true });
    expect(errors).toHaveBeenCalled();
    errors.mockRestore();
  });
});
