import { A2UI_OPERATIONS_KEY } from "@ag-ui/a2ui-toolkit";
import {
  type ActivitySnapshotEvent,
  type BaseEvent,
  EventType,
  type StateDeltaEvent,
  type StateSnapshotEvent,
} from "@ag-ui/client";
import { MemorySaver } from "@langchain/langgraph";
import { BOARD_SURFACE_ID_PREFIX } from "@repo/shared/a2ui/board-catalog";
import { CHAT_SURFACE_ID_PREFIX } from "@repo/shared/a2ui/chat-catalog";
import {
  DELETE_BOARD_SURFACE_TOOL,
  READ_BOARD_SURFACE_TOOL,
  RENDER_SURFACE_TOOL,
  UPDATE_BOARD_SURFACE_TOOL,
} from "@repo/shared/constants/agents";
import {
  type BoardSurface,
  initialLearningState,
  type LearningState,
  type SurfaceComponent,
} from "@repo/shared/schemas";
import { applyPatch } from "fast-json-patch";
import { v4 as uuidv4 } from "uuid";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  BOARD_EMPTY,
  BOARD_SURFACE_NOT_FOUND,
  NO_SURFACE_IDS,
  SURFACE_ERROR_PREFIX,
} from "../../../constants/tools";
import { createChatModel } from "../../llm/chat-model";
import {
  createHandler,
  type Handler,
  lastMessages,
  lastSnapshot,
  readCheckpoint,
  runTurn,
  textOf,
  toolResultsOf,
  userMessage,
} from "./runtime-harness";
import { isAfterTool, scriptAgents } from "./scripted-agents";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

const CHAT_TREE: SurfaceComponent[] = [
  { id: "root", component: "Panel", title: "HTTP", children: ["intro"] },
  { id: "intro", component: "Paragraph", text: "GET reads, POST writes." },
];

const BOARD_TREE: SurfaceComponent[] = [
  { id: "root", component: "Stack", children: ["intro", "terms"] },
  { id: "intro", component: "Paragraph", text: "Git keeps history." },
  { id: "terms", component: "TagList", tags: ["commit", "branch"] },
];

/** Drafts (its root and first child are complete) but names a missing child. */
const BROKEN_TREE: SurfaceComponent[] = [
  { id: "root", component: "Stack", children: ["intro", "missing"] },
  { id: "intro", component: "Paragraph", text: "Half a view." },
];

const REPLY = "Here you go.";

let checkpointer: MemorySaver;
let handler: Handler;
let threadId: string;

/**
 * A Supervisor that makes the tool call `call` returns for the student's
 * message, then replies once the tool has returned.
 */
const callTool = (
  call: (text: string) => { name: string; args: Record<string, unknown> },
) =>
  scriptAgents((messages) =>
    isAfterTool(messages)
      ? { text: REPLY }
      : { toolCalls: [call(messages.at(-1)?.text ?? "")] },
  );

const send = (
  content: string,
  previous: BaseEvent[] = [],
): Promise<BaseEvent[]> =>
  runTurn(handler, {
    threadId,
    messages: [...lastMessages(previous), userMessage(content)],
    state: lastSnapshot(previous),
  });

/**
 * The state the browser holds after each event: a new thread's state, then
 * the run's snapshots and deltas applied.
 */
const browserStates = (events: BaseEvent[]): LearningState[] => {
  let state = initialLearningState;
  return events.map((event) => {
    if (event.type === EventType.STATE_SNAPSHOT) {
      state = structuredClone(
        (event as StateSnapshotEvent).snapshot as LearningState,
      );
    } else if (event.type === EventType.STATE_DELTA) {
      state = applyPatch(
        structuredClone(state),
        (event as StateDeltaEvent).delta,
      ).newDocument;
    }
    return state;
  });
};

const boardOf = (events: BaseEvent[]): BoardSurface[] =>
  (browserStates(events).at(-1)?.board ?? []) as BoardSurface[];

/** Puts one view on the Board and returns the turn's events. */
const drawBoardView = async (): Promise<BaseEvent[]> => {
  callTool(() => ({
    name: RENDER_SURFACE_TOOL,
    args: { target: "canvas", title: "Git", components: BOARD_TREE },
  }));
  return send("put git on the board");
};

beforeEach(() => {
  vi.mocked(createChatModel).mockReset();
  checkpointer = new MemorySaver();
  handler = createHandler({ checkpointer });
  threadId = uuidv4();
});

describe("renderSurface in the chat", () => {
  it("draws the surface in the chat and leaves the Board alone", async () => {
    callTool(() => ({
      name: RENDER_SURFACE_TOOL,
      args: { target: "chat", title: "HTTP", components: CHAT_TREE },
    }));

    const events = await send("compare http methods");

    const [result] = toolResultsOf(events) as Record<string, unknown>[];
    expect(result).toHaveProperty(A2UI_OPERATIONS_KEY);
    expect(JSON.stringify(result)).toContain(CHAT_SURFACE_ID_PREFIX);
    expect(
      events.some(
        (event) =>
          event.type === EventType.ACTIVITY_SNAPSHOT &&
          JSON.stringify((event as ActivitySnapshotEvent).content).includes(
            CHAT_SURFACE_ID_PREFIX,
          ),
      ),
    ).toBe(true);
    expect(boardOf(events)).toEqual([]);
    // The surface is the whole reply.
    expect(textOf(events)).toBe("");
  });

  it("returns the errors of an invalid tree so it can be fixed", async () => {
    callTool(() => ({
      name: RENDER_SURFACE_TOOL,
      args: { target: "chat", title: "Board only", components: BOARD_TREE },
    }));

    const events = await send("compare http methods");

    const [result] = toolResultsOf(events) as { error: string }[];
    expect(result?.error.startsWith(SURFACE_ERROR_PREFIX)).toBe(true);
    expect(textOf(events)).toBe(REPLY);
  });
});

describe("renderSurface on the Board", () => {
  it("saves the view and tells the Supervisor which one it was", async () => {
    const events = await drawBoardView();

    const [view] = boardOf(events);
    expect(view).toMatchObject({ title: "Git", revision: 1 });
    expect(view?.id.startsWith(BOARD_SURFACE_ID_PREFIX)).toBe(true);
    expect(JSON.stringify(view?.operations)).toContain("Git keeps history.");
    expect(toolResultsOf(events)).toEqual([
      { surface: { id: view?.id, title: "Git", revision: 1 } },
    ]);
    expect(await readCheckpoint(checkpointer, threadId)).toMatchObject({
      board: [{ id: view?.id, revision: 1 }],
      boardDraft: null,
    });
    expect(textOf(events)).toBe("");
  });

  it("streams a draft that the view replaces without a gap", async () => {
    const states = browserStates(await drawBoardView());

    const drafted = states.findIndex(({ boardDraft }) => boardDraft !== null);
    const saved = states.findIndex(({ board }) => board.length > 0);
    expect(drafted).toBeGreaterThanOrEqual(0);
    expect(states[drafted]?.boardDraft?.id).toMatch(
      new RegExp(`^${BOARD_SURFACE_ID_PREFIX}draft-`),
    );
    expect(saved).toBeGreaterThan(drafted);
    // The draft shows until the view does, and never after it.
    expect(
      states.slice(drafted, saved).every(({ boardDraft }) => boardDraft),
    ).toBe(true);
    expect(states.slice(saved).every(({ boardDraft }) => !boardDraft)).toBe(
      true,
    );
  });

  it("clears the draft of a tree that fails validation", async () => {
    callTool(() => ({
      name: RENDER_SURFACE_TOOL,
      args: { target: "canvas", title: "Broken", components: BROKEN_TREE },
    }));

    const events = await send("put a broken view on the board");

    const states = browserStates(events);
    expect(states.some(({ boardDraft }) => boardDraft !== null)).toBe(true);
    expect(states.at(-1)).toMatchObject({ board: [], boardDraft: null });
    expect(textOf(events)).toBe(REPLY);
  });

  it("keeps the newest views when the Board is full", async () => {
    let events: BaseEvent[] = [];
    for (let index = 1; index <= 9; index += 1) {
      callTool(() => ({
        name: RENDER_SURFACE_TOOL,
        args: {
          target: "canvas",
          title: `View ${index}`,
          components: BOARD_TREE,
        },
      }));
      events = await send(`view ${index}`, events);
    }

    expect(boardOf(events).map(({ title }) => title)).toEqual(
      [2, 3, 4, 5, 6, 7, 8, 9].map((index) => `View ${index}`),
    );
    // Nine whole turns: about 3 s alone, past the 5 s default under load.
  });
});

describe("editing the Board", () => {
  it("reads a view's components", async () => {
    const first = await drawBoardView();
    const [view] = boardOf(first);
    callTool(() => ({
      name: READ_BOARD_SURFACE_TOOL,
      args: { surfaceId: view?.id },
    }));

    const events = await send("what is on the git view", first);

    expect(toolResultsOf(events)).toEqual([
      { surfaceId: view?.id, title: "Git", components: BOARD_TREE },
    ]);
  });

  it("revises a view under its id and moves it to the top", async () => {
    let events = await drawBoardView();
    const [git] = boardOf(events);
    callTool(() => ({
      name: RENDER_SURFACE_TOOL,
      args: { target: "canvas", title: "Docker", components: BOARD_TREE },
    }));
    events = await send("put docker on the board", events);
    callTool(() => ({
      name: UPDATE_BOARD_SURFACE_TOOL,
      args: {
        surfaceId: git?.id,
        title: "Git basics",
        components: BOARD_TREE.slice(0, 2).map((component) =>
          component.id === "root"
            ? { ...component, children: ["intro"] }
            : component,
        ),
      },
    }));

    events = await send("drop the tags from the git view", events);

    const board = boardOf(events);
    expect(board.map(({ title }) => title)).toEqual(["Docker", "Git basics"]);
    expect(board.at(-1)).toMatchObject({ id: git?.id, revision: 2 });
    expect(JSON.stringify(board.at(-1)?.operations)).not.toContain("branch");
    expect(toolResultsOf(events)).toEqual([
      { surface: { id: git?.id, title: "Git basics", revision: 2 } },
    ]);
  });

  it("drafts a revision under the id of the view it revises", async () => {
    const first = await drawBoardView();
    const [view] = boardOf(first);
    callTool(() => ({
      name: UPDATE_BOARD_SURFACE_TOOL,
      args: { surfaceId: view?.id, title: "Git", components: BOARD_TREE },
    }));

    const states = browserStates(await send("tweak the git view", first));

    expect(states.find(({ boardDraft }) => boardDraft)?.boardDraft?.id).toBe(
      view?.id,
    );
    expect(states.at(-1)?.boardDraft).toBeNull();
  });

  it("names the views there are when an id matches none", async () => {
    const first = await drawBoardView();
    const [view] = boardOf(first);
    callTool(() => ({
      name: UPDATE_BOARD_SURFACE_TOOL,
      args: { surfaceId: "board-nope", title: "Git", components: BOARD_TREE },
    }));

    const events = await send("tweak the view", first);

    expect(toolResultsOf(events)).toEqual([
      { error: `${BOARD_SURFACE_NOT_FOUND} ${view?.id} ("Git").` },
    ]);
    expect(boardOf(events)).toEqual(boardOf(first));
  });

  it("says the Board is empty when there is nothing to read", async () => {
    callTool(() => ({
      name: READ_BOARD_SURFACE_TOOL,
      args: { surfaceId: "board-1" },
    }));

    expect(toolResultsOf(await send("read the board"))).toEqual([
      { error: BOARD_EMPTY },
    ]);
  });
});

describe("deleteBoardSurface", () => {
  it("removes the views it names and returns them", async () => {
    const first = await drawBoardView();
    const [view] = boardOf(first);
    callTool(() => ({
      name: DELETE_BOARD_SURFACE_TOOL,
      args: { surfaceIds: [view?.id, "board-unknown"] },
    }));

    const events = await send("clear the board", first);

    expect(boardOf(events)).toEqual([]);
    expect(toolResultsOf(events)).toEqual([
      { removed: [{ id: view?.id, title: "Git" }] },
    ]);
    expect(await readCheckpoint(checkpointer, threadId)).toMatchObject({
      board: [],
    });
    expect(textOf(events)).toBe("");
  });

  it("removes nothing without a matching id", async () => {
    const first = await drawBoardView();
    for (const [surfaceIds, error] of [
      [[], NO_SURFACE_IDS],
      [["board-unknown"], BOARD_SURFACE_NOT_FOUND],
    ] as const) {
      callTool(() => ({
        name: DELETE_BOARD_SURFACE_TOOL,
        args: { surfaceIds: [...surfaceIds] },
      }));

      const events = await send("delete it", first);

      const [result] = toolResultsOf(events) as { error: string }[];
      expect(result?.error.startsWith(error)).toBe(true);
      expect(boardOf(events)).toEqual(boardOf(first));
    }
  });
});
