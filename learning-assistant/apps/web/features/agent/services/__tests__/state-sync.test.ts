import { type BaseEvent, EventType } from "@ag-ui/client";
import { initialLearningState } from "@repo/shared/schemas";
import { firstValueFrom, from, toArray } from "rxjs";
import { describe, expect, it } from "vitest";

import { syncStateFromTools } from "@/features/agent/services/state-sync";

const run = (events: BaseEvent[]) =>
  firstValueFrom(
    from(events).pipe(syncStateFromTools(initialLearningState), toArray()),
  );

const started: BaseEvent[] = [
  { type: EventType.RUN_STARTED, threadId: "t", runId: "r" } as BaseEvent,
];
const finished = {
  type: EventType.RUN_FINISHED,
  threadId: "t",
  runId: "r",
} as BaseEvent;

const createToolStartEvent = (toolCallName: string) =>
  ({
    type: EventType.TOOL_CALL_START,
    toolCallId: "c1",
    toolCallName,
  }) as BaseEvent;

const createToolResultEvent = (content: unknown) =>
  ({
    type: EventType.TOOL_CALL_RESULT,
    messageId: "m1",
    toolCallId: "c1",
    content: JSON.stringify(content),
  }) as BaseEvent;

describe("syncStateFromTools", () => {
  it("emits STATE_DELTA after a subagent's start and result", async () => {
    const events = await run([
      ...started,
      createToolStartEvent("makeNotes"),
      createToolResultEvent({ ok: true, data: { markdown: "# Notes" } }),
      finished,
    ]);

    expect(events.map((e) => e.type)).toEqual([
      EventType.RUN_STARTED,
      EventType.TOOL_CALL_START,
      EventType.STATE_DELTA,
      EventType.TOOL_CALL_RESULT,
      EventType.STATE_DELTA,
      EventType.RUN_FINISHED,
    ]);
  });

  it("passes other tools through untouched", async () => {
    const events = await run([
      ...started,
      createToolStartEvent("render_a2ui"),
      createToolResultEvent({ ok: true }),
      finished,
    ]);
    expect(events.some((e) => e.type === EventType.STATE_DELTA)).toBe(false);
  });

  it("clears a task left running before the run ends", async () => {
    const events = await run([
      ...started,
      createToolStartEvent("research"),
      finished,
    ]);

    expect(events.map((e) => e.type)).toEqual([
      EventType.RUN_STARTED,
      EventType.TOOL_CALL_START,
      EventType.STATE_DELTA,
      EventType.STATE_DELTA,
      EventType.RUN_FINISHED,
    ]);
  });
});
