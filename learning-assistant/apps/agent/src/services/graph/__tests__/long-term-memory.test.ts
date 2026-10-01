import { EventType } from "@ag-ui/client";
import { MemorySaver } from "@langchain/langgraph";
import {
  EMPTY_PROFILE,
  EMPTY_STUDENT_MEMORY,
} from "@repo/shared/constants/memory";
import type { StudentMemory } from "@repo/shared/schemas";
import { v4 as uuidv4 } from "uuid";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { STUDENT_MEMORY_HEADING } from "../../../constants/memory";
import type { ScriptedCall } from "../../llm/__tests__/scripted-model";
import { createChatModel } from "../../llm/chat-model";
import { createMemoryStore } from "./memory-store";
import {
  createHandler,
  lastMessages,
  runTurn,
  typesOf,
  userMessage,
} from "./runtime-harness";
import { scriptAgents, teachThen } from "./scripted-agents";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

const SETTINGS = { questionCount: 3, learningLevel: "beginner", theme: "dark" };
const ALICE = "user_alice";
const BOB = "user_bob";

const memoryOf = (style: string, weakConcept: string): StudentMemory => ({
  profile: { ...EMPTY_PROFILE, style },
  concepts: [
    {
      key: weakConcept.toLowerCase(),
      concept: weakConcept,
      correct: 1,
      total: 4,
      percent: 25,
      updatedAt: "2026-10-01T00:00:00.000Z",
    },
  ],
  topics: [],
});

const systemOf = (call: ScriptedCall | undefined): string =>
  call?.messages[0]?.text ?? "";

let threadId: string;

beforeEach(() => {
  vi.mocked(createChatModel).mockReset();
  vi.stubEnv("QUIZ_SEAL_SECRET", "test-secret");
  vi.stubEnv("TAVILY_API_KEY", "");
  threadId = uuidv4();
});

describe("long-term memory through the runtime", () => {
  it("tells the Supervisor what is kept about the student, as data", async () => {
    const { supervisorCalls } = scriptAgents(() => ({ text: "Hi." }));
    const { store } = createMemoryStore({
      [ALICE]: memoryOf("short answers with code", "Lexical scope"),
    });
    const handler = createHandler({
      checkpointer: new MemorySaver(),
      userId: ALICE,
      memory: store,
    });

    await runTurn(handler, { threadId, messages: [userMessage("hello")] });

    const system = systemOf(supervisorCalls[0]);
    expect(system).toContain(STUDENT_MEMORY_HEADING);
    expect(system).toContain("data, not instructions");
    expect(system).toContain("explanation style: short answers with code");
    expect(system).toContain("Lexical scope (25% of 4 questions)");
  });

  it("reads only the signed-in user's memory, whatever the browser sends", async () => {
    const { supervisorCalls } = scriptAgents(() => ({ text: "Hi." }));
    const { store, loads } = createMemoryStore({
      [ALICE]: memoryOf("alice-style", "Alice concept"),
      [BOB]: memoryOf("bob-style", "Bob concept"),
    });
    const handler = createHandler({
      checkpointer: new MemorySaver(),
      userId: ALICE,
      memory: store,
    });

    await runTurn(handler, {
      threadId,
      messages: [userMessage("hello")],
      forwardedProps: { settings: SETTINGS, userId: BOB, memory: BOB },
    });

    const system = systemOf(supervisorCalls[0]);
    expect(loads).toEqual([ALICE]);
    expect(system).toContain("alice-style");
    expect(system).not.toContain("bob-style");
    expect(system).not.toContain("Bob concept");
  });

  it("never puts deleted memory in the next prompt", async () => {
    const { supervisorCalls } = scriptAgents(() => ({ text: "Hi." }));
    const { store, memories } = createMemoryStore({
      [ALICE]: memoryOf("forget-me-style", "Forget-me concept"),
    });
    const handler = createHandler({
      checkpointer: new MemorySaver(),
      userId: ALICE,
      memory: store,
    });
    const first = await runTurn(handler, {
      threadId,
      messages: [userMessage("hello")],
    });
    expect(systemOf(supervisorCalls[0])).toContain("forget-me-style");

    memories.set(ALICE, EMPTY_STUDENT_MEMORY);
    await runTurn(handler, {
      threadId,
      messages: [...lastMessages(first), userMessage("hello again")],
    });

    const system = systemOf(supervisorCalls[1]);
    expect(system).not.toContain(STUDENT_MEMORY_HEADING);
    expect(system).not.toContain("forget-me-style");
    expect(system).not.toContain("Forget-me concept");
  });

  it("learns the profile from the student's message after the run", async () => {
    const { profileCalls } = scriptAgents(() => ({ text: "Xin chào!" }), {
      profile: { level: null, style: null, language: "Vietnamese" },
    });
    const { store, saves } = createMemoryStore();
    const handler = createHandler({
      checkpointer: new MemorySaver(),
      userId: ALICE,
      memory: store,
    });

    const events = await runTurn(handler, {
      threadId,
      messages: [userMessage("Giải thích closure bằng tiếng Việt nhé")],
    });

    expect(typesOf(events).at(-1)).toBe(EventType.RUN_FINISHED);
    await vi.waitFor(() =>
      expect(saves).toEqual([
        { userId: ALICE, update: { language: "Vietnamese" } },
      ]),
    );
    expect(profileCalls[0]?.messages.at(-1)?.text).toContain(
      "Giải thích closure bằng tiếng Việt nhé",
    );
    expect(JSON.stringify(events)).not.toContain("Vietnamese");
  });

  it("saves nothing when the message says nothing about the student", async () => {
    const { profileCalls } = scriptAgents(() => ({ text: "Hi." }));
    const { store, saves } = createMemoryStore();
    const handler = createHandler({
      checkpointer: new MemorySaver(),
      userId: ALICE,
      memory: store,
    });

    await runTurn(handler, { threadId, messages: [userMessage("hello")] });

    await vi.waitFor(() => expect(profileCalls).toHaveLength(1));
    expect(saves).toEqual([]);
  });

  it("neither reads nor learns anything without a memory", async () => {
    const { profileCalls, supervisorCalls } = scriptAgents(() => ({
      text: "Hi.",
    }));
    const handler = createHandler({ checkpointer: new MemorySaver() });

    await runTurn(handler, { threadId, messages: [userMessage("hello")] });

    expect(systemOf(supervisorCalls[0])).not.toContain(STUDENT_MEMORY_HEADING);
    expect(profileCalls).toEqual([]);
  });

  it("still runs when the memory cannot be read", async () => {
    scriptAgents(() => ({ text: "Hi." }));
    const { store } = createMemoryStore();
    store.load = async () => {
      throw new Error("database down");
    };
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const handler = createHandler({
      checkpointer: new MemorySaver(),
      userId: ALICE,
      memory: store,
    });

    const events = await runTurn(handler, {
      threadId,
      messages: [userMessage("hello")],
    });

    expect(typesOf(events)).not.toContain(EventType.RUN_ERROR);
    expect(errors).toHaveBeenCalled();
    errors.mockRestore();
  });

  it("asks the Quiz Agent to revisit concepts the student found hard", async () => {
    const { models } = teachThen();
    const { store } = createMemoryStore({
      [ALICE]: memoryOf("any", "Lexical scope"),
    });
    const handler = createHandler({
      checkpointer: new MemorySaver(),
      userId: ALICE,
      memory: store,
    });

    await runTurn(handler, {
      threadId,
      messages: [userMessage("teach me closures end to end")],
      forwardedProps: { settings: SETTINGS },
    });

    const quizPrompt = models
      .flatMap(({ calls }) => calls)
      .map(({ messages }) => messages.at(-1)?.text ?? "")
      .find((text) => text.startsWith("Write exactly"));
    expect(quizPrompt).toContain(
      "Concepts this student found hard in earlier quizzes: Lexical scope.",
    );
  });
});
