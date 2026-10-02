import { type BaseEvent, EventType, type StateDeltaEvent } from "@ag-ui/client";
import { MemorySaver } from "@langchain/langgraph";
import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import { EMPTY_PROFILE } from "@repo/shared/constants/memory";
import type { Quiz } from "@repo/shared/schemas";
import { v4 as uuidv4 } from "uuid";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CLIENT_VISIBLE_STATE_KEYS } from "../../../constants/graph";
import { createChatModel } from "../../llm/chat-model";
import { SUPERVISOR_PROMPT } from "../../prompts/supervisor";
import { createMemoryStore } from "./memory-store";
import {
  connect,
  createHandler,
  type Handler,
  lastMessages,
  lastSnapshot,
  runTurn,
  snapshotsOf,
  typesOf,
  userMessage,
} from "./runtime-harness";
import { teachThen } from "./scripted-agents";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

const SETTINGS = { questionCount: 3, learningLevel: "beginner", theme: "dark" };
const ANSWERS = { q1: 1, q2: 0, q3: 3 };
const USER_ID = "user_alice";
const API_KEY = "sk-stream-test-key";
const MEMORY_STYLE = "memory-style-never-streamed";
const MEMORY_CONCEPT = "Memory concept never streamed";

/** What the graph keeps for itself; none of it may reach the browser. */
const SERVER_ONLY_TEXT = [
  API_KEY,
  MEMORY_STYLE,
  MEMORY_CONCEPT,
  SUPERVISOR_PROMPT.slice(0, 40),
  "rawEvent",
  "pendingSubmit",
  "summarizedUpTo",
];

let handler: Handler;
let threadId: string;
let memoryLoads: string[];

const quizOf = (events: BaseEvent[]) => lastSnapshot(events).quiz as Quiz;

/** Research → learning material → quiz, a Submit, then a reload. */
const runWholePath = async () => {
  const quizzed = await runTurn(handler, {
    threadId,
    messages: [userMessage("teach me closures end to end")],
    forwardedProps: { settings: SETTINGS },
  });
  const graded = await runTurn(handler, {
    threadId,
    messages: lastMessages(quizzed),
    state: {
      ...lastSnapshot(quizzed),
      quiz: { ...quizOf(quizzed), answers: ANSWERS },
    },
    forwardedProps: {
      settings: SETTINGS,
      a2uiAction: {
        userAction: {
          name: QUIZ_ACTIONS.submit,
          surfaceId: "quiz",
          context: { quizId: quizOf(quizzed).id, answers: ANSWERS },
        },
      },
    },
  });
  const reloaded = await connect(handler, threadId);
  return { quizzed, graded, reloaded };
};

beforeEach(() => {
  vi.mocked(createChatModel).mockReset();
  vi.stubEnv("QUIZ_SEAL_SECRET", "test-secret");
  vi.stubEnv("TAVILY_API_KEY", "");
  const { store, loads } = createMemoryStore({
    [USER_ID]: {
      profile: { ...EMPTY_PROFILE, style: MEMORY_STYLE },
      concepts: [
        {
          key: MEMORY_CONCEPT.toLowerCase(),
          concept: MEMORY_CONCEPT,
          correct: 0,
          total: 2,
          percent: 0,
          updatedAt: "2026-10-01T00:00:00.000Z",
        },
      ],
      topics: [],
    },
  });
  memoryLoads = loads;
  handler = createHandler({
    checkpointer: new MemorySaver(),
    apiKey: API_KEY,
    userId: USER_ID,
    memory: store,
  });
  threadId = uuidv4();
});

describe("what reaches the browser over a whole learning path", () => {
  it("sends no raw graph events and nothing the graph keeps for itself", async () => {
    teachThen();
    const streams = await runWholePath();

    for (const events of Object.values(streams)) {
      expect(events.length).toBeGreaterThan(0);
      expect(typesOf(events)).not.toContain(EventType.RAW);
      const text = JSON.stringify(events);
      for (const secret of SERVER_ONLY_TEXT) {
        expect(text).not.toContain(secret);
      }
    }
  });

  it("sends only the canvas's state keys, in snapshots and in deltas", async () => {
    teachThen();
    const streams = await runWholePath();

    for (const events of Object.values(streams)) {
      for (const snapshot of snapshotsOf(events)) {
        expect(
          Object.keys(snapshot).filter(
            (key) => !CLIENT_VISIBLE_STATE_KEYS.includes(key),
          ),
        ).toEqual([]);
      }
      const deltaKeys = events
        .filter(({ type }) => type === EventType.STATE_DELTA)
        .flatMap((event) => (event as StateDeltaEvent).delta)
        .map(({ path }: { path: string }) => path.split("/")[1] ?? "");
      expect(
        deltaKeys.filter((key) => !CLIENT_VISIBLE_STATE_KEYS.includes(key)),
      ).toEqual([]);
    }
  });

  it("really ran the path it checks, with the student's memory read", async () => {
    teachThen();
    const { quizzed, graded, reloaded } = await runWholePath();

    expect(lastSnapshot(quizzed)).toMatchObject({ stage: "quiz" });
    expect(lastSnapshot(graded)).toMatchObject({
      stage: "evaluation",
      quiz: { answers: ANSWERS, submitted: true },
    });
    expect(lastSnapshot(reloaded)).toMatchObject({ stage: "evaluation" });
    expect(memoryLoads).toContain(USER_ID);
  });
});
