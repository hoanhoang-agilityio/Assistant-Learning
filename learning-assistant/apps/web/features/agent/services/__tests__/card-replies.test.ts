import { type BaseEvent, EventType, type Message } from "@ag-ui/client";
import { firstValueFrom, from, toArray } from "rxjs";
import { describe, expect, it } from "vitest";

import { muteRepliesAfterCards } from "@/features/agent/services/card-replies";

const start = (toolCallId: string, toolCallName: string) =>
  ({ type: EventType.TOOL_CALL_START, toolCallId, toolCallName }) as BaseEvent;
const result = (toolCallId: string, content: unknown) =>
  ({
    type: EventType.TOOL_CALL_RESULT,
    messageId: `m-${toolCallId}`,
    toolCallId,
    content: typeof content === "string" ? content : JSON.stringify(content),
  }) as BaseEvent;
const text = (messageId: string, delta: string) =>
  ({
    type: EventType.TEXT_MESSAGE_CHUNK,
    role: "assistant",
    messageId,
    delta,
  }) as BaseEvent;

const replies = async (events: BaseEvent[], history: Message[] = []) =>
  (
    await firstValueFrom(
      from(events).pipe(muteRepliesAfterCards(history), toArray()),
    )
  ).flatMap((event) =>
    event.type === EventType.TEXT_MESSAGE_CHUNK
      ? [(event as BaseEvent & { delta: string }).delta]
      : [],
  );

const toolHistory = (name: string, content: string): Message[] => [
  { id: "u", role: "user", content: "hi" },
  {
    id: "a",
    role: "assistant",
    toolCalls: [
      { id: "c", type: "function", function: { name, arguments: "{}" } },
    ],
  },
  { id: "t", role: "tool", toolCallId: "c", content },
];

describe("muteRepliesAfterCards", () => {
  it("drops the reply after a successful subagent tool", async () => {
    expect(
      await replies([
        start("a", "research"),
        result("a", { ok: true, data: {} }),
        text("m1", "Research is on the canvas."),
      ]),
    ).toEqual([]);
  });

  it("lets the reply through after a failed tool", async () => {
    expect(
      await replies([
        start("a", "generateQuiz"),
        result("a", { ok: false, error: "No material." }),
        text("m1", "Make learning material first."),
      ]),
    ).toEqual(["Make learning material first."]);
  });

  it("lets the reply through after a surface tool returns errors", async () => {
    expect(
      await replies([
        start("a", "renderSurface"),
        result("a", { error: "Invalid tree." }),
        text("m1", "Sorry."),
      ]),
    ).toEqual(["Sorry."]);
  });

  it("keeps tool calls flowing on autopilot while muting text", async () => {
    const events = await firstValueFrom(
      from([
        start("a", "research"),
        result("a", { ok: true, data: {} }),
        text("m1", "Now the material."),
        start("b", "makeMaterial"),
        result("b", { ok: true, data: {} }),
      ]).pipe(muteRepliesAfterCards([]), toArray()),
    );

    expect(events.map(({ type }) => type)).toEqual([
      EventType.TOOL_CALL_START,
      EventType.TOOL_CALL_RESULT,
      EventType.TOOL_CALL_START,
      EventType.TOOL_CALL_RESULT,
    ]);
  });

  it("lets the reply through after a tool with no card", async () => {
    expect(
      await replies([
        start("a", "readBoardSurface"),
        result("a", { components: [] }),
        text("m1", "That view is empty."),
      ]),
    ).toEqual(["That view is empty."]);
  });

  it("drops the reply when the history ends with a frontend card result", async () => {
    expect(
      await replies(
        [text("m1", "Switched to dark.")],
        toolHistory("setTheme", "Theme is now dark."),
      ),
    ).toEqual([]);
  });

  it("answers a new question after a card", async () => {
    expect(
      await replies(
        [text("m1", "Hello!")],
        [
          ...toolHistory("setTheme", "Theme is now dark."),
          { id: "u2", role: "user", content: "hello" },
        ],
      ),
    ).toEqual(["Hello!"]);
  });
});
