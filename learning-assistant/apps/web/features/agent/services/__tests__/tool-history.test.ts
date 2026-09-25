import {
  type BaseEvent,
  EventType,
  type Message,
  type ToolCallResultEvent,
} from "@ag-ui/client";
import { firstValueFrom, from, toArray } from "rxjs";
import { describe, expect, it } from "vitest";

import { LOST_TOOL_RESULT } from "@/features/agent/constants/errors";
import {
  closeLostToolCalls,
  repairToolHistory,
} from "@/features/agent/services/tool-history";

const start = (toolCallId: string, toolCallName: string) =>
  ({ type: EventType.TOOL_CALL_START, toolCallId, toolCallName }) as BaseEvent;
const result = (toolCallId: string) =>
  ({
    type: EventType.TOOL_CALL_RESULT,
    messageId: `m-${toolCallId}`,
    toolCallId,
    content: "{}",
  }) as BaseEvent;
const finished = {
  type: EventType.RUN_FINISHED,
  threadId: "t",
  runId: "r",
} as BaseEvent;

const run = (events: BaseEvent[], clientTools: string[] = []) =>
  firstValueFrom(
    from(events).pipe(closeLostToolCalls(new Set(clientTools)), toArray()),
  );

describe("closeLostToolCalls", () => {
  it("adds a failure result for a server call that never returned", async () => {
    const events = await run([start("a", "updateBoardSurface"), finished]);

    expect(events.map(({ type }) => type)).toEqual([
      EventType.TOOL_CALL_START,
      EventType.TOOL_CALL_RESULT,
      EventType.RUN_FINISHED,
    ]);
    expect(events[1]).toMatchObject({ toolCallId: "a" });
    expect(JSON.parse((events[1] as ToolCallResultEvent).content)).toEqual({
      ok: false,
      error: LOST_TOOL_RESULT,
    });
  });

  it("closes a call to a tool that does not exist", async () => {
    const events = await run([start("a", "deleteEverything"), finished]);
    expect(events.map(({ type }) => type)).toContain(
      EventType.TOOL_CALL_RESULT,
    );
  });

  it("leaves answered calls and the client's own tools alone", async () => {
    const events = await run(
      [start("a", "research"), result("a"), start("b", "setTheme"), finished],
      ["setTheme"],
    );

    expect(
      events.filter(({ type }) => type === EventType.TOOL_CALL_RESULT),
    ).toHaveLength(1);
  });
});

const assistant = (id: string, toolCallIds: string[]): Message => ({
  id,
  role: "assistant",
  content: "",
  toolCalls: toolCallIds.map((toolCallId) => ({
    id: toolCallId,
    type: "function",
    function: { name: "updateBoardSurface", arguments: "{}" },
  })),
});
const tool = (toolCallId: string): Message => ({
  id: `t-${toolCallId}`,
  role: "tool",
  toolCallId,
  content: "{}",
});
const user = (id: string): Message => ({ id, role: "user", content: "hi" });

describe("repairToolHistory", () => {
  it("adds a failure result right after the call that has none", () => {
    const repaired = repairToolHistory([
      user("u1"),
      assistant("a1", ["call-1", "call-2"]),
      tool("call-2"),
      user("u2"),
    ]);

    expect(repaired.map(({ id }) => id)).toEqual([
      "u1",
      "a1",
      "lost-call-1",
      "t-call-2",
      "u2",
    ]);
    expect(repaired[2]).toMatchObject({ role: "tool", toolCallId: "call-1" });
  });

  it("returns a complete history unchanged", () => {
    const messages = [user("u1"), assistant("a1", ["c"]), tool("c")];
    expect(repairToolHistory(messages)).toEqual(messages);
  });
});
