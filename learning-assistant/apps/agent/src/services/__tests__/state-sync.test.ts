import { type BaseEvent, EventType } from "@ag-ui/client";
import {
  DELETE_BOARD_SURFACE_TOOL,
  RENDER_SURFACE_TOOL,
  UPDATE_BOARD_SURFACE_TOOL,
} from "@repo/shared/constants/agents";
import { initialLearningState, type LearningState } from "@repo/shared/schemas";
import { firstValueFrom, from, toArray } from "rxjs";
import { describe, expect, it } from "vitest";

import { DRAFT_EVENTS } from "../../constants/agents";
import { LOST_TOOL_RESULT } from "../../constants/errors";
import { syncStateFromTools } from "../state-sync";
import { closeLostToolCalls } from "../tool-history";

const quiz = {
  id: "q1",
  questions: [
    {
      id: "a",
      concept: "Closures",
      question: "What does a closure capture?",
      options: ["Values", "Bindings", "Types", "Nothing"],
    },
  ],
  answers: {},
  answerKeySealed: "sealed",
  submitted: false,
};

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
      createToolStartEvent("makeMaterial"),
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

  it("adds a canvas renderSurface result to the Board", async () => {
    const surface = {
      id: "board-1",
      title: "Overview",
      operations: [],
      revision: 1,
    };
    const events = await run([
      ...started,
      createToolStartEvent(RENDER_SURFACE_TOOL),
      createToolResultEvent({ surface }),
      finished,
    ]);

    expect(events.map((e) => e.type)).toEqual([
      EventType.RUN_STARTED,
      EventType.TOOL_CALL_START,
      EventType.TOOL_CALL_RESULT,
      EventType.STATE_DELTA,
      EventType.RUN_FINISHED,
    ]);
    expect(events[3]).toMatchObject({
      delta: [{ op: "add", path: "/board", value: [surface] }],
    });
  });

  it("writes an updateBoardSurface result to the Board", async () => {
    const surface = {
      id: "board-1",
      title: "Overview",
      operations: [],
      revision: 2,
    };
    const events = await run([
      ...started,
      createToolStartEvent(UPDATE_BOARD_SURFACE_TOOL),
      createToolResultEvent({ surface }),
      finished,
    ]);

    expect(events[3]).toMatchObject({
      type: EventType.STATE_DELTA,
      delta: [{ op: "add", path: "/board", value: [surface] }],
    });
  });

  it("takes a deleteBoardSurface result's views off the Board", async () => {
    const surface = {
      id: "board-1",
      title: "Overview",
      operations: [],
      revision: 1,
    };
    const events = await firstValueFrom(
      from([
        ...started,
        createToolStartEvent(DELETE_BOARD_SURFACE_TOOL),
        createToolResultEvent({
          removed: [{ id: "board-1", title: "Overview" }],
        }),
        finished,
      ]).pipe(
        syncStateFromTools({ ...initialLearningState, board: [surface] }),
        toArray(),
      ),
    );

    expect(events[3]).toMatchObject({
      type: EventType.STATE_DELTA,
      delta: [{ op: "add", path: "/board", value: [] }],
    });
  });

  it("leaves the state alone for a chat renderSurface result", async () => {
    const events = await run([
      ...started,
      createToolStartEvent(RENDER_SURFACE_TOOL),
      createToolResultEvent({ a2ui_operations: [] }),
      finished,
    ]);

    expect(events.map((e) => e.type)).not.toContain(EventType.STATE_DELTA);
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

  it("turns a running subagent's draft into state and drops the event", async () => {
    const draft = { task: "material", markdown: "# Clo" };
    const events = await run([
      ...started,
      createToolStartEvent("makeMaterial"),
      { type: EventType.CUSTOM, name: DRAFT_EVENTS.stage, value: draft },
      createToolResultEvent({ ok: true, data: { markdown: "# Closures" } }),
      finished,
    ] as BaseEvent[]);

    expect(events.map((e) => e.type)).toEqual([
      EventType.RUN_STARTED,
      EventType.TOOL_CALL_START,
      EventType.STATE_DELTA,
      EventType.STATE_DELTA,
      EventType.TOOL_CALL_RESULT,
      EventType.STATE_DELTA,
      EventType.RUN_FINISHED,
    ]);
    expect(events[3]).toMatchObject({
      delta: [{ op: "add", path: "/draft", value: draft }],
    });
    expect(events[5]).toMatchObject({
      delta: expect.arrayContaining([
        { op: "add", path: "/draft", value: null },
      ]),
    });
  });

  it("turns a Board draft into state and passes other custom events", async () => {
    const other = { type: EventType.CUSTOM, name: "other", value: 1 };
    const events = await run([
      ...started,
      createToolStartEvent(RENDER_SURFACE_TOOL),
      {
        type: EventType.CUSTOM,
        name: DRAFT_EVENTS.board,
        value: {
          toolCallId: "c1",
          toolCallName: RENDER_SURFACE_TOOL,
          args: {
            target: "canvas",
            title: "Overview",
            components: [{ id: "root", component: "Stack", children: [] }],
          },
        },
      },
      other,
      finished,
    ] as BaseEvent[]);

    expect(events.map((e) => e.type)).toEqual([
      EventType.RUN_STARTED,
      EventType.TOOL_CALL_START,
      EventType.STATE_DELTA,
      EventType.CUSTOM,
      // The run ended before the result, so the draft is cleared.
      EventType.STATE_DELTA,
      EventType.RUN_FINISHED,
    ]);
    expect(events[2]).toMatchObject({
      delta: [{ op: "add", path: "/boardDraft" }],
    });
    expect(events[3]).toBe(other);
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

describe("closeLostToolCalls then syncStateFromTools", () => {
  const before: LearningState = { ...initialLearningState, quiz };

  /** The final state after a quiz call that never returned. */
  const runLostQuizCall = async (signal: AbortSignal) => {
    let state = before;
    await firstValueFrom(
      from([...started, createToolStartEvent("generateQuiz"), finished]).pipe(
        closeLostToolCalls(new Set(), signal),
        syncStateFromTools(before, (next) => {
          state = next;
        }),
        toArray(),
      ),
    );
    return state;
  };

  it("clears a stopped task without an error and keeps the old quiz", async () => {
    const controller = new AbortController();
    controller.abort();

    expect(await runLostQuizCall(controller.signal)).toEqual({
      ...before,
      status: { running: null },
    });
  });

  it("still fails a lost call when the run was not stopped", async () => {
    const state = await runLostQuizCall(new AbortController().signal);

    expect(state.status).toEqual({
      running: null,
      error: LOST_TOOL_RESULT,
      failed: "quiz",
    });
    expect(state.quiz).toEqual(quiz);
  });
});
