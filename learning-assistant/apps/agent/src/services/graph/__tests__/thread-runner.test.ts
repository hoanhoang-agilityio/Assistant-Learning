import {
  EventType,
  type MessagesSnapshotEvent,
  type StateSnapshotEvent,
} from "@ag-ui/client";
import { HumanMessage } from "@langchain/core/messages";
import { MemorySaver } from "@langchain/langgraph";
import { EMPTY_STUDENT_MEMORY } from "@repo/shared/constants/memory";
import { DEFAULT_SETTINGS } from "@repo/shared/constants/settings";
import { initialLearningState } from "@repo/shared/schemas";
import { v4 as uuidv4 } from "uuid";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RELOAD_RUN_ID } from "../../../constants/graph";
import type { RunContext } from "../../../schemas/graph";
import { ScriptedModel } from "../../llm/__tests__/scripted-model";
import { createChatModel } from "../../llm/chat-model";
import { createLearningGraph } from "../learning-graph";
import { NO_RECORDS } from "../no-records";
import {
  connect,
  createHandler,
  runTurn,
  userMessage,
} from "./runtime-harness";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

const REPLY = "Hello! What would you like to learn today?";

const RUN_CONTEXT: RunContext = {
  userId: "user_1",
  settings: DEFAULT_SETTINGS,
  appContext: [],
  submit: null,
  memory: EMPTY_STUDENT_MEMORY,
};

let checkpointer: MemorySaver;
let threadId: string;

beforeEach(() => {
  vi.mocked(createChatModel).mockReturnValue(
    new ScriptedModel(() => ({ text: REPLY })) as never,
  );
  checkpointer = new MemorySaver();
  threadId = uuidv4();
});

/**
 * Writes a thread straight into the checkpointer, as if another process (or
 * this one before a restart) had run it: the runner holds no events for it.
 */
const runElsewhere = async () => {
  const graph = createLearningGraph({
    model: new ScriptedModel(() => ({ text: REPLY })),
    apiKey: "sk-test",
    checkpointer,
    records: NO_RECORDS,
  });
  await graph.invoke(
    {
      messages: [new HumanMessage({ id: uuidv4(), content: "hi" })],
      reflection: { rating: 4, text: "Clear notes" },
    },
    { configurable: { thread_id: threadId }, context: RUN_CONTEXT },
  );
};

describe("reloading a thread", () => {
  it("replays a run this process streamed", async () => {
    const handler = createHandler({ checkpointer });
    await runTurn(handler, { threadId, messages: [userMessage("hi")] });

    const events = await connect(handler, threadId);

    const types = events.map(({ type }) => type);
    expect(types).toContain(EventType.TEXT_MESSAGE_CONTENT);
    expect(JSON.stringify(events)).not.toContain(RELOAD_RUN_ID);
  });

  it("rebuilds messages and state from the checkpoint when it holds no events", async () => {
    await runElsewhere();

    const events = await connect(createHandler({ checkpointer }), threadId);

    expect(events.map(({ type }) => type)).toEqual([
      EventType.RUN_STARTED,
      EventType.STATE_SNAPSHOT,
      EventType.MESSAGES_SNAPSHOT,
      EventType.RUN_FINISHED,
    ]);
    const [, state, messages] = events;
    expect((state as StateSnapshotEvent).snapshot).toEqual({
      ...initialLearningState,
      reflection: { rating: 4, text: "Clear notes" },
    });
    expect(
      (messages as MessagesSnapshotEvent).messages.map(({ role, content }) => [
        role,
        content,
      ]),
    ).toEqual([
      ["user", "hi"],
      ["assistant", REPLY],
    ]);
  });

  it("sends nothing for a thread that does not exist", async () => {
    const events = await connect(createHandler({ checkpointer }), threadId);

    expect(events).toEqual([]);
  });
});
