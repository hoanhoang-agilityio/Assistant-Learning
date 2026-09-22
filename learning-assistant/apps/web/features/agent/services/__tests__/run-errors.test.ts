import {
  type BaseEvent,
  EventType,
  type TextMessageContentEvent,
} from "@ag-ui/client";
import { firstValueFrom, from, toArray } from "rxjs";
import { describe, expect, it } from "vitest";

import { RUN_ERROR_INTRO } from "@/features/agent/constants/errors";
import { explainRunErrors } from "@/features/agent/services/run-errors";

const run = (events: BaseEvent[]) =>
  firstValueFrom(
    from(events).pipe(
      explainRunErrors((message) => `explained: ${message}`),
      toArray(),
    ),
  );

describe("explainRunErrors", () => {
  it("puts an assistant message in front of RUN_ERROR", async () => {
    const events = await run([
      { type: EventType.RUN_STARTED },
      { type: EventType.RUN_ERROR, message: "401" } as BaseEvent,
    ]);

    expect(events.map((e) => e.type)).toEqual([
      EventType.RUN_STARTED,
      EventType.TEXT_MESSAGE_START,
      EventType.TEXT_MESSAGE_CONTENT,
      EventType.TEXT_MESSAGE_END,
      EventType.RUN_ERROR,
    ]);
    expect((events[2] as TextMessageContentEvent).delta).toBe(
      `${RUN_ERROR_INTRO} explained: 401`,
    );
  });

  it("passes a successful run through unchanged", async () => {
    const events: BaseEvent[] = [
      { type: EventType.RUN_STARTED },
      { type: EventType.RUN_FINISHED },
    ];
    expect(await run(events)).toEqual(events);
  });
});
