import type { BaseEvent } from "@ag-ui/client";
import { MemorySaver } from "@langchain/langgraph";
import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import {
  NEW_CONVERSATION_REQUIREMENT,
  SET_THEME_TOOL,
} from "@repo/shared/constants/agents";
import {
  initialLearningState,
  type Material,
  type Quiz,
} from "@repo/shared/schemas";
import { v4 as uuidv4 } from "uuid";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UNANSWERED_TOOL_RESULT } from "../../../constants/errors";
import { NEW_CONVERSATION_INSTRUCTION } from "../../../constants/tools";
import { createChatModel } from "../../llm/chat-model";
import {
  createHandler,
  type Handler,
  lastMessages,
  lastSnapshot,
  readCheckpoint,
  runTurn,
  snapshotsOf,
  textOf,
  toolCallsOf,
  toolResultsOf,
  userMessage,
} from "./runtime-harness";
import {
  isAfterTool,
  lastHumanText,
  MATERIAL,
  teachThen,
} from "./scripted-agents";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

const SETTINGS = { questionCount: 3, learningLevel: "beginner", theme: "dark" };
const ANSWERS = { q1: 1, q2: 0, q3: 3 };
const NEW_TOPIC_REPLY = "Press New topic to learn about black holes.";

const frontendTool = (name: string) => ({
  name,
  description: name,
  parameters: { type: "object", properties: {} },
});

let checkpointer: MemorySaver;
let handler: Handler;
let threadId: string;

const quizOf = (events: BaseEvent[]) => lastSnapshot(events).quiz as Quiz;
const materialOf = (events: BaseEvent[]) =>
  lastSnapshot(events).material as Material;

const reachQuiz = () =>
  runTurn(handler, {
    threadId,
    messages: [userMessage("teach me closures end to end")],
    forwardedProps: { settings: SETTINGS },
  });

/** The next chat message, sent with the state the browser holds (`state`). */
const chat = (
  previous: BaseEvent[],
  state: Record<string, unknown>,
  content = "hello",
) =>
  runTurn(handler, {
    threadId,
    messages: [...lastMessages(previous), userMessage(content)],
    state,
    forwardedProps: { settings: SETTINGS },
    tools: [frontendTool(SET_THEME_TOOL)],
  });

const submit = (previous: BaseEvent[]) =>
  runTurn(handler, {
    threadId,
    messages: lastMessages(previous),
    state: {
      ...lastSnapshot(previous),
      quiz: { ...quizOf(previous), answers: ANSWERS },
    },
    forwardedProps: {
      settings: SETTINGS,
      a2uiAction: {
        userAction: {
          name: QUIZ_ACTIONS.submit,
          surfaceId: "quiz",
          context: { quizId: quizOf(previous).id, answers: ANSWERS },
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

describe("what the browser changed since the last run", () => {
  it("keeps the answers it picked and nothing else of its quiz", async () => {
    teachThen();
    const quizzed = await reachQuiz();

    const events = await chat(quizzed, {
      ...lastSnapshot(quizzed),
      stage: "score",
      quiz: {
        ...quizOf(quizzed),
        answers: { q1: 2, q9: 0 },
        submitted: true,
        answerKeySealed: "forged",
        questions: [],
      },
      score: { percent: 100, tier: "Master" },
    });

    expect(lastSnapshot(events)).toMatchObject({
      stage: "quiz",
      score: null,
      quiz: { ...quizOf(quizzed), answers: { q1: 2 } },
    });
  });

  it("takes an edit of the learning material and clears the quiz written from it", async () => {
    const { supervisorCalls } = teachThen();
    const quizzed = await reachQuiz();

    const events = await chat(quizzed, {
      ...lastSnapshot(quizzed),
      material: { ...materialOf(quizzed), original: "# My own notes" },
    });

    const edited = {
      stage: "material",
      material: {
        original: "# My own notes",
        simplified: null,
        view: "original",
      },
      quiz: null,
      quizOutdated: true,
    };
    expect(lastSnapshot(events)).toMatchObject(edited);
    // The canvas never goes back to the old text during the run.
    expect(snapshotsOf(events).at(0)).toMatchObject(edited);
    expect(await readCheckpoint(checkpointer, threadId)).toMatchObject(edited);
    // The Supervisor reads the state as edited, too.
    const system = supervisorCalls.at(-1)?.messages[0]?.text ?? "";
    expect(system).toContain('"quiz": null');
    expect(system).toContain('"quizOutdated": true');
  });

  it("clears the results when the student retakes a graded quiz", async () => {
    teachThen();
    const graded = await submit(await reachQuiz());
    expect(lastSnapshot(graded)).toMatchObject({ stage: "evaluation" });

    const events = await chat(graded, {
      ...lastSnapshot(graded),
      quiz: { ...quizOf(graded), answers: {} },
    });

    expect(lastSnapshot(events)).toMatchObject({
      stage: "quiz",
      quiz: { answers: {}, submitted: false },
      evaluation: null,
      score: null,
      feedback: null,
    });
  });

  it("saves a reflection once there is feedback to reflect on", async () => {
    teachThen();
    const quizzed = await reachQuiz();
    const reflection = { rating: 4, text: "Clear notes" };

    const early = await chat(quizzed, { ...lastSnapshot(quizzed), reflection });
    expect(lastSnapshot(early)).toMatchObject({ reflection: null });

    const graded = await submit(early);
    const events = await chat(graded, { ...lastSnapshot(graded), reflection });
    expect(lastSnapshot(events)).toMatchObject({ reflection });
  });
});

describe("a new topic", () => {
  /** Researches whatever the student names; points them to "New topic" when refused. */
  const researchOnRequest = () =>
    teachThen((messages) => {
      const last = messages.at(-1);
      if (last?.type === "tool") {
        return last.text.includes(NEW_CONVERSATION_REQUIREMENT)
          ? { text: NEW_TOPIC_REPLY }
          : { text: "Done." };
      }
      return lastHumanText(messages).startsWith("research")
        ? { toolCalls: [{ name: "research", args: { topic: "black holes" } }] }
        : { text: "Done." };
    });

  it("is never researched over this conversation's work", async () => {
    researchOnRequest();
    const quizzed = await reachQuiz();

    const events = await chat(
      quizzed,
      lastSnapshot(quizzed),
      "research black holes",
    );

    expect(toolCallsOf(events)).toEqual(["research"]);
    expect(toolResultsOf(events)).toEqual([
      {
        ok: false,
        requires: NEW_CONVERSATION_REQUIREMENT,
        topic: "black holes",
        instruction: NEW_CONVERSATION_INSTRUCTION,
      },
    ]);
    expect(textOf(events)).toBe(NEW_TOPIC_REPLY);
    expect(lastSnapshot(events)).toEqual(lastSnapshot(quizzed));
  });

  it("keeps the work even when the browser sends a cleared state", async () => {
    researchOnRequest();
    const quizzed = await reachQuiz();

    const events = await chat(quizzed, initialLearningState, "hello");

    expect(lastSnapshot(events)).toMatchObject({
      stage: "quiz",
      material: { original: MATERIAL.markdown },
    });
  });
});

describe("a tool call left without a result", () => {
  it("is answered for the model, not in the thread", async () => {
    const { supervisorCalls } = teachThen((messages) =>
      lastHumanText(messages) === "dark please" && !isAfterTool(messages)
        ? { toolCalls: [{ name: SET_THEME_TOOL, args: { theme: "dark" } }] }
        : { text: "Hello again." },
    );
    const asked = await chat([], {}, "dark please");

    await chat(asked, lastSnapshot(asked), "never mind, hello");

    const seen = supervisorCalls.at(-1)?.messages ?? [];
    expect(seen.map((message) => message.type)).toEqual([
      "system",
      "human",
      "ai",
      "tool",
      "human",
    ]);
    expect(seen[3]?.text).toContain(UNANSWERED_TOOL_RESULT);
    const thread = await readCheckpoint(checkpointer, threadId);
    expect(thread?.messages.map((message) => message.type)).toEqual([
      "human",
      "ai",
      "human",
      "ai",
    ]);
  });
});
