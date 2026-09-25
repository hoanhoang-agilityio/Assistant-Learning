import { type BaseEvent, EventType } from "@ag-ui/client";
import { RENDER_SURFACE_TOOL } from "@repo/shared/constants/agents";
import { firstValueFrom, from, toArray } from "rxjs";
import { describe, expect, it, vi } from "vitest";

import {
  DRAFT_EVENTS,
  DRAFT_INTERVAL_MS,
} from "@/features/agent/constants/agents";
import {
  streamBoardDrafts,
  throttleDrafts,
} from "@/features/agent/services/drafts";

const start = (toolCallName: string): BaseEvent =>
  ({
    type: EventType.TOOL_CALL_START,
    toolCallId: "c1",
    toolCallName,
  }) as BaseEvent;
const args = (delta: string): BaseEvent =>
  ({ type: EventType.TOOL_CALL_ARGS, toolCallId: "c1", delta }) as BaseEvent;

/** A clock that moves one interval on every read. */
const createTickingClock = () => {
  let time = 0;
  return () => (time += DRAFT_INTERVAL_MS);
};

const run = (events: BaseEvent[], now: () => number) =>
  firstValueFrom(from(events).pipe(streamBoardDrafts(now), toArray()));

describe("throttleDrafts", () => {
  it("drops calls closer together than the interval", () => {
    let time = 0;
    const fn = vi.fn();
    const report = throttleDrafts(fn, () => time);

    report(1);
    time += DRAFT_INTERVAL_MS - 1;
    report(2);
    time += 1;
    report(3);

    expect(fn.mock.calls).toEqual([[1], [3]]);
  });
});

describe("streamBoardDrafts", () => {
  it("follows a surface call's args with its partial arguments", async () => {
    const events = await run(
      [
        start(RENDER_SURFACE_TOOL),
        args('{"target":"canvas","ti'),
        args('tle":"Over'),
      ],
      createTickingClock(),
    );

    expect(events.map((e) => e.type)).toEqual([
      EventType.TOOL_CALL_START,
      EventType.TOOL_CALL_ARGS,
      EventType.CUSTOM,
      EventType.TOOL_CALL_ARGS,
      EventType.CUSTOM,
    ]);
    expect(events[4]).toMatchObject({
      name: DRAFT_EVENTS.board,
      value: {
        toolCallId: "c1",
        toolCallName: RENDER_SURFACE_TOOL,
        args: { target: "canvas", title: "Over" },
      },
    });
  });

  it("drafts at most once per interval", async () => {
    const events = await run(
      [start(RENDER_SURFACE_TOOL), args('{"a":'), args("1"), args("}")],
      () => 0,
    );

    expect(events.filter((e) => e.type === EventType.CUSTOM)).toHaveLength(1);
  });

  it("leaves other tools' args alone", async () => {
    const events = await run(
      [start("research"), args('{"topic":"x"}')],
      createTickingClock(),
    );

    expect(events.map((e) => e.type)).toEqual([
      EventType.TOOL_CALL_START,
      EventType.TOOL_CALL_ARGS,
    ]);
  });
});
