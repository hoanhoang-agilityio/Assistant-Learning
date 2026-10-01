import { type BaseEvent, EventType, type Message } from "@ag-ui/client";
import { MemorySaver } from "@langchain/langgraph";
import { v4 as uuidv4 } from "uuid";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CONVERSATION_SUMMARY_HEADING } from "../../../constants/memory";
import { createChatModel } from "../../llm/chat-model";
import {
  connect,
  createHandler,
  type Handler,
  lastMessages,
  readCheckpoint,
  runTurn,
  typesOf,
  userMessage,
} from "./runtime-harness";
import { scriptAgents, SUMMARY } from "./scripted-agents";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

// A budget a two-turn chat passes, and only the current turn kept verbatim.
vi.mock("../../../constants/memory", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../constants/memory")>()),
  SUMMARY_TRIGGER_TOKENS: 50,
  SUMMARY_KEEP_TURNS: 1,
}));

const PADDING = "z".repeat(200);
const QUESTIONS = ["first question", "second question", "third question"];

let checkpointer: MemorySaver;
let handler: Handler;
let threadId: string;

const readThread = async () => {
  const values = await readCheckpoint(checkpointer, threadId);
  if (!values) {
    throw new Error("The thread has no checkpoint");
  }
  return values;
};

/** Asks each question in turn, as the browser does: the whole thread each time. */
const chat = async (questions: string[]) => {
  const runs: BaseEvent[][] = [];
  let messages: Message[] = [];
  for (const question of questions) {
    const events = await runTurn(handler, {
      threadId,
      messages: [...messages, userMessage(question)],
    });
    runs.push(events);
    messages = lastMessages(events);
  }
  return runs;
};

beforeEach(() => {
  vi.mocked(createChatModel).mockReset();
  checkpointer = new MemorySaver();
  handler = createHandler({ checkpointer });
  threadId = uuidv4();
});

describe("the conversation summary through the runtime", () => {
  it("folds older turns into a summary and keeps every message", async () => {
    const { summaryCalls } = scriptAgents(() => ({
      text: `Answer ${PADDING}`,
    }));

    await chat(QUESTIONS.slice(0, 1));
    expect(summaryCalls).toEqual([]);
    const before = (await readThread()).messages.map(({ id, text }) => ({
      id,
      text,
    }));

    await chat(QUESTIONS.slice(1, 2));
    const thread = await readThread();
    expect(summaryCalls).toHaveLength(1);
    expect(thread.summary).toBe(SUMMARY);
    expect(thread.summarizedUpTo).toBe(before.at(-1)?.id);
    expect(
      thread.messages.slice(0, 2).map(({ id, text }) => ({ id, text })),
    ).toEqual(before);
    expect(thread.messages.map(({ type }) => type)).toEqual([
      "human",
      "ai",
      "human",
      "ai",
    ]);
    expect(summaryCalls[0]?.messages.at(-1)?.text).toContain(
      "Student: first question",
    );
  });

  it("gives the Supervisor the summary in place of the folded messages", async () => {
    const { supervisorCalls, summaryCalls } = scriptAgents(() => ({
      text: `Answer ${PADDING}`,
    }));

    await chat(QUESTIONS);

    const last = supervisorCalls.at(-1);
    const [system, ...messages] = last?.messages ?? [];
    expect(system?.text).toContain(`${CONVERSATION_SUMMARY_HEADING}\n`);
    expect(system?.text).toContain(SUMMARY);
    const texts = messages.map(({ text }) => text);
    expect(texts).not.toContain("first question");
    expect(texts).toContain("second question");
    expect(texts).toContain("third question");

    // The next fold reads the earlier summary and only the new messages.
    const refold = summaryCalls[1]?.messages.at(-1)?.text ?? "";
    expect(refold).toContain(`Earlier summary:\n${SUMMARY}`);
    expect(refold).not.toContain("first question");
    expect(refold).toContain("Student: second question");
  });

  it("never sends the summary to the browser, during a run or on reload", async () => {
    scriptAgents(() => ({ text: `Answer ${PADDING}` }));

    const runs = await chat(QUESTIONS);
    const reload = await connect(handler, threadId);

    expect((await readThread()).summary).toBe(SUMMARY);
    for (const events of [...runs, reload]) {
      const stream = JSON.stringify(events);
      expect(stream).not.toContain(SUMMARY);
      expect(stream).not.toContain("summarizedUpTo");
    }
    expect(lastMessages(reload).map(({ content }) => content)).toContain(
      "first question",
    );
  });

  it("leaves the run and the thread as they were when summarising fails", async () => {
    scriptAgents(() => ({ text: `Answer ${PADDING}` }), {
      summary: new Error("model down"),
    });
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});

    const runs = await chat(QUESTIONS.slice(0, 2));

    expect(typesOf(runs[1] ?? [])).not.toContain(EventType.RUN_ERROR);
    expect(typesOf(runs[1] ?? []).at(-1)).toBe(EventType.RUN_FINISHED);
    const thread = await readThread();
    expect(thread.summary).toBeNull();
    expect(thread.summarizedUpTo).toBeNull();
    expect(thread.messages).toHaveLength(4);
    expect(errors).toHaveBeenCalled();
    errors.mockRestore();
  });
});
