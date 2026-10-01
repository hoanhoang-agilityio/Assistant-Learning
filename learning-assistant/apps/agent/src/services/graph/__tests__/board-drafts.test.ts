import { type BaseEvent, EventType, type StateDeltaEvent } from "@ag-ui/client";
import { initialLearningState } from "@repo/shared/schemas";
import { firstValueFrom, from, toArray } from "rxjs";
import { describe, expect, it } from "vitest";

import { DRAFT_INTERVAL_MS } from "../../../constants/agents";
import { streamBoardDrafts } from "../board-drafts";

const ROOT = { id: "root", component: "Stack", children: ["p1"] };
const PARAGRAPH = { id: "p1", component: "Paragraph", text: "Hello" };

const snapshot = {
  type: EventType.STATE_SNAPSHOT,
  snapshot: initialLearningState,
} as BaseEvent;
const start = {
  type: EventType.TOOL_CALL_START,
  toolCallId: "c1",
  toolCallName: "renderSurface",
} as BaseEvent;
const args = (delta: string): BaseEvent =>
  ({ type: EventType.TOOL_CALL_ARGS, toolCallId: "c1", delta }) as BaseEvent;
const finished = { type: EventType.RUN_FINISHED } as BaseEvent;

/** A clock that moves one interval on every read. */
const createTickingClock = () => {
  let time = 0;
  return () => (time += DRAFT_INTERVAL_MS);
};

const run = (events: BaseEvent[]) =>
  firstValueFrom(
    from(events).pipe(streamBoardDrafts(createTickingClock()), toArray()),
  );

const deltasOf = (events: BaseEvent[]) =>
  events
    .filter(({ type }) => type === EventType.STATE_DELTA)
    .map((event) => (event as StateDeltaEvent).delta);

/** Args that grow from a view with only its root to one with a paragraph. */
const growing = (): BaseEvent[] => {
  const whole = JSON.stringify({
    target: "canvas",
    title: "Overview",
    components: [ROOT, PARAGRAPH],
  });
  const cut = whole.indexOf(`{"id":"p1"`);
  return [args(whole.slice(0, cut)), args(whole.slice(cut))];
};

describe("streamBoardDrafts", () => {
  it("sends the whole draft first, then what grew inside it", async () => {
    const deltas = deltasOf(await run([snapshot, start, ...growing()]));

    expect(deltas[0]).toEqual([
      expect.objectContaining({ op: "add", path: "/boardDraft" }),
    ]);
    expect(
      deltas[1]?.every(({ path }) => path.startsWith("/boardDraft/")),
    ).toBe(true);
  });

  it("ignores a surface for the chat", async () => {
    const events = await run([
      snapshot,
      start,
      args(
        JSON.stringify({ target: "chat", title: "Card", components: [ROOT] }),
      ),
    ]);

    expect(deltasOf(events)).toEqual([]);
  });

  it("clears a draft the run ends without", async () => {
    const events = await run([snapshot, start, ...growing(), finished]);

    expect(deltasOf(events).at(-1)).toEqual([
      { op: "add", path: "/boardDraft", value: null },
    ]);
    expect(events.at(-1)).toBe(finished);
  });
});
