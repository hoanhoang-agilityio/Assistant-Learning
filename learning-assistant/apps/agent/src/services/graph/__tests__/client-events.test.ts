import { type BaseEvent, EventType } from "@ag-ui/client";
import { initialLearningState } from "@repo/shared/schemas";
import { firstValueFrom, from, toArray } from "rxjs";
import { describe, expect, it } from "vitest";

import { RUN_ERROR_INTRO } from "../../../constants/errors";
import { MANUAL_STATE_EVENT } from "../../../constants/graph";
import { toClientEvents } from "../client-events";

const run = (events: BaseEvent[]) =>
  firstValueFrom(from(events).pipe(toClientEvents([]), toArray()));

const snapshot = (values: Record<string, unknown>): BaseEvent =>
  ({ type: EventType.STATE_SNAPSHOT, snapshot: values }) as BaseEvent;

describe("toClientEvents", () => {
  it("drops RAW events and the graph event attached to the others", async () => {
    const events = await run([
      { type: EventType.RUN_STARTED, rawEvent: { summary: "server only" } },
      { type: EventType.RAW, event: { summary: "server only" } } as BaseEvent,
      { type: EventType.RUN_FINISHED },
    ]);

    expect(events).toEqual([
      { type: EventType.RUN_STARTED },
      { type: EventType.RUN_FINISHED },
    ]);
  });

  it("drops the custom event that repeats a state a tool sent", async () => {
    const events = await run([
      {
        type: EventType.CUSTOM,
        name: MANUAL_STATE_EVENT,
        value: initialLearningState,
      } as BaseEvent,
      { type: EventType.CUSTOM, name: "other", value: 1 } as BaseEvent,
    ]);

    expect(events).toEqual([
      { type: EventType.CUSTOM, name: "other", value: 1 },
    ]);
  });

  it("keeps only the canvas state in a snapshot", async () => {
    const events = await run([
      snapshot({
        ...initialLearningState,
        messages: [{ content: "hi" }],
        tools: [],
        copilotkit: { actions: [] },
        summary: "server only",
      }),
    ]);

    expect(events).toEqual([snapshot(initialLearningState)]);
  });

  it("drops a snapshot equal to the last one sent", async () => {
    const researched = { ...initialLearningState, topic: "Closures" };

    const events = await run([
      snapshot(initialLearningState),
      snapshot({ ...initialLearningState, messages: [{ content: "hi" }] }),
      { type: EventType.STEP_FINISHED } as BaseEvent,
      snapshot(initialLearningState),
      snapshot(researched),
      snapshot(initialLearningState),
    ]);

    expect(events).toEqual([
      snapshot(initialLearningState),
      { type: EventType.STEP_FINISHED },
      snapshot(researched),
      snapshot(initialLearningState),
    ]);
  });

  it("explains a failed run, keeps its snapshots and ends with the error", async () => {
    const events = await run([
      { type: EventType.RUN_STARTED },
      { type: EventType.RUN_ERROR, message: "429 rate limit" } as BaseEvent,
      { type: EventType.STEP_FINISHED } as BaseEvent,
      snapshot(initialLearningState),
      { type: EventType.MESSAGES_SNAPSHOT, messages: [] } as BaseEvent,
      { type: EventType.RUN_FINISHED },
    ]);

    expect(events.map(({ type }) => type)).toEqual([
      EventType.RUN_STARTED,
      EventType.STATE_SNAPSHOT,
      EventType.MESSAGES_SNAPSHOT,
      EventType.TEXT_MESSAGE_START,
      EventType.TEXT_MESSAGE_CONTENT,
      EventType.TEXT_MESSAGE_END,
      EventType.RUN_ERROR,
    ]);
  });

  it("drops the text a run streams after a card tool succeeds", async () => {
    const events = await run([
      {
        type: EventType.TOOL_CALL_START,
        toolCallId: "c1",
        toolCallName: "research",
      } as BaseEvent,
      {
        type: EventType.TOOL_CALL_RESULT,
        toolCallId: "c1",
        messageId: "m1",
        content: '{"ok":true,"data":{}}',
      } as BaseEvent,
      {
        type: EventType.TEXT_MESSAGE_START,
        messageId: "m2",
        role: "assistant",
      } as BaseEvent,
      {
        type: EventType.TEXT_MESSAGE_CONTENT,
        messageId: "m2",
        delta: "Done!",
      } as BaseEvent,
      { type: EventType.TEXT_MESSAGE_END, messageId: "m2" } as BaseEvent,
    ]);

    expect(events.map(({ type }) => type)).toEqual([
      EventType.TOOL_CALL_START,
      EventType.TOOL_CALL_RESULT,
    ]);
  });

  it("blanks the same text in a message snapshot and keeps what explains a failure", async () => {
    const call = (id: string, name: string) => ({
      id: `a-${id}`,
      role: "assistant" as const,
      content: "",
      toolCalls: [
        { id, type: "function" as const, function: { name, arguments: "{}" } },
      ],
    });
    const messages = [
      call("c1", "research"),
      {
        id: "t1",
        role: "tool" as const,
        toolCallId: "c1",
        content: '{"ok":true,"data":{}}',
      },
      { id: "a1", role: "assistant" as const, content: "Research is ready!" },
      call("c2", "makeMaterial"),
      {
        id: "t2",
        role: "tool" as const,
        toolCallId: "c2",
        content: '{"ok":false,"error":"No research."}',
      },
      { id: "a2", role: "assistant" as const, content: "That failed because…" },
      call("c3", "research"),
      {
        id: "t3",
        role: "tool" as const,
        toolCallId: "c3",
        content: '{"ok":true,"data":{}}',
      },
      {
        id: "a3",
        role: "assistant" as const,
        content: `${RUN_ERROR_INTRO} OpenAI is busy.`,
      },
    ];

    const [event] = await run([
      { type: EventType.MESSAGES_SNAPSHOT, messages } as BaseEvent,
    ]);

    expect(event).toEqual({
      type: EventType.MESSAGES_SNAPSHOT,
      messages: messages.map((message) =>
        message.id === "a1" ? { ...message, content: "" } : message,
      ),
    });
  });
});
