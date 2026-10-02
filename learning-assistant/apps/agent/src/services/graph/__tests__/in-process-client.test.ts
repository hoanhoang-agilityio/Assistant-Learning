import { MemorySaver } from "@langchain/langgraph";
import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import { v4 as uuidv4 } from "uuid";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TURN_RUN_NAMES } from "../../../constants/graph";
import { createChatModel } from "../../llm/chat-model";
import { createInProcessClient } from "../in-process-client";
import { createLearningGraph } from "../learning-graph";
import { NO_RECORDS } from "../no-records";
import { isAfterTool, scriptAgents } from "./scripted-agents";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

const USER_ID = "user_42";
const API_KEY = "sk-trace-test-key";

/** A graph event as the client yields it: what LangSmith records per step. */
interface GraphEvent {
  event: string;
  name: string;
  run_id: string;
  parent_ids?: string[];
  metadata: Record<string, unknown>;
}

/** Runs one turn through the client and returns the graph's own events. */
const streamTurn = async (payload: Record<string, unknown>) => {
  scriptAgents((messages) =>
    isAfterTool(messages)
      ? { text: "Done." }
      : { toolCalls: [{ name: "research", args: { topic: "closures" } }] },
  );
  const graph = createLearningGraph({
    model: createChatModel(API_KEY),
    apiKey: API_KEY,
    checkpointer: new MemorySaver(),
    records: NO_RECORDS,
  });
  const client = createInProcessClient({
    graph,
    userId: USER_ID,
    records: NO_RECORDS,
  });
  const threadId = uuidv4();

  const events: GraphEvent[] = [];
  for await (const chunk of client.runs.stream(threadId, "learning", {
    input: { messages: [{ type: "human", content: "research closures" }] },
    ...payload,
  })) {
    if (chunk.event === "events") {
      events.push(chunk.data as GraphEvent);
    }
  }
  return { threadId, events };
};

beforeEach(() => {
  vi.mocked(createChatModel).mockReset();
  vi.stubEnv("QUIZ_SEAL_SECRET", "test-secret");
  vi.stubEnv("TAVILY_API_KEY", "");
});

describe("tracing", () => {
  it("tags every step of a turn with the thread and the user", async () => {
    const { threadId, events } = await streamTurn({});

    expect(events.length).toBeGreaterThan(0);
    for (const { metadata } of events) {
      expect(metadata).toMatchObject({ thread_id: threadId, user_id: USER_ID });
    }
    // The subagent's own model call is part of the same trace.
    expect(
      events.some(
        ({ event, metadata }) =>
          event === "on_chat_model_stream" &&
          metadata["emit-messages"] === false,
      ),
    ).toBe(true);
  });

  it("never records the user's API key in a step", async () => {
    const { events } = await streamTurn({});

    expect(events.length).toBeGreaterThan(0);
    expect(JSON.stringify(events)).not.toContain(API_KEY);
  });

  it("names the turn by what started it", async () => {
    const rootName = (events: GraphEvent[]) =>
      events.find(
        ({ event, parent_ids: parents = [] }) =>
          event === "on_chain_start" && parents.length === 0,
      )?.name;

    const chat = await streamTurn({});
    const submit = await streamTurn({
      a2uiAction: {
        userAction: {
          name: QUIZ_ACTIONS.submit,
          context: { quizId: "q", answers: {} },
        },
      },
    });

    expect(rootName(chat.events)).toBe(TURN_RUN_NAMES.chat);
    expect(rootName(submit.events)).toBe(TURN_RUN_NAMES.submit);
  });
});
