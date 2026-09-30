import { type BaseEvent, EventType } from "@ag-ui/client";
import { initialLearningState } from "@repo/shared/schemas";
import { firstValueFrom, from, toArray } from "rxjs";
import { describe, expect, it } from "vitest";

import { toClientEvents } from "../client-events";

const run = (events: BaseEvent[]) =>
  firstValueFrom(from(events).pipe(toClientEvents(), toArray()));

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

  it("explains a failed run and ends at its error", async () => {
    const events = await run([
      { type: EventType.RUN_STARTED },
      { type: EventType.RUN_ERROR, message: "429 rate limit" } as BaseEvent,
      snapshot(initialLearningState),
      { type: EventType.RUN_FINISHED },
    ]);

    expect(events.map(({ type }) => type)).toEqual([
      EventType.RUN_STARTED,
      EventType.TEXT_MESSAGE_START,
      EventType.TEXT_MESSAGE_CONTENT,
      EventType.TEXT_MESSAGE_END,
      EventType.RUN_ERROR,
    ]);
  });
});
