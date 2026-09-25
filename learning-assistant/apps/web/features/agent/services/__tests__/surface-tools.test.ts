import { A2UI_OPERATIONS_KEY } from "@ag-ui/a2ui-toolkit";
import {
  BOARD_CATALOG_ID,
  BOARD_SURFACE_ID_PREFIX,
} from "@repo/shared/a2ui/board-catalog";
import {
  CHAT_CATALOG_ID,
  CHAT_SURFACE_ID_PREFIX,
} from "@repo/shared/a2ui/chat-catalog";
import {
  DELETE_BOARD_SURFACE_TOOL,
  READ_BOARD_SURFACE_TOOL,
  RENDER_SURFACE_TOOL,
  UPDATE_BOARD_SURFACE_TOOL,
} from "@repo/shared/constants/agents";
import {
  type BoardSurface,
  BoardSurfaceResultSchema,
  initialLearningState,
  RenderSurfaceArgsSchema,
  type SurfaceComponent,
  type SurfaceTarget,
} from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import {
  BOARD_EMPTY,
  BOARD_SURFACE_NOT_FOUND,
  NO_SURFACE_IDS,
  SURFACE_ERROR_PREFIX,
} from "@/features/agent/constants/tools";
import { createTestContext } from "@/features/agent/services/__tests__/quiz-fixtures";
import { createSurfaceTools } from "@/features/agent/services/tools/surface-tools";

const CHAT_TREE: SurfaceComponent[] = [
  {
    id: "root",
    component: "Panel",
    title: "HTTP methods",
    children: ["intro", "table"],
  },
  { id: "intro", component: "Paragraph", text: "Each method has one job." },
  {
    id: "table",
    component: "Table",
    columns: ["Method", "Use"],
    rows: [
      ["GET", "Read"],
      ["POST", "Create"],
    ],
  },
];

const BOARD_TREE: SurfaceComponent[] = [
  { id: "root", component: "Stack", children: ["cols"] },
  { id: "cols", component: "Columns", children: ["article", "tip"] },
  {
    id: "article",
    component: "ArticleCard",
    eyebrow: "Overview",
    title: "HTTP methods",
    body: "Each method has one job.",
  },
  { id: "tip", component: "Callout", tone: "tip", text: "GET is safe." },
];

/** The surface tools over a state holding `board`. */
const createTools = (board: BoardSurface[] = []) => {
  const { ctx } = createTestContext({ ...initialLearningState, board });
  const tools = createSurfaceTools(ctx);
  const call = (name: string, args: object) =>
    tools.find((tool) => tool.name === name)?.execute?.(args) as Promise<
      Record<string, unknown>
    >;
  return {
    render: (target: SurfaceTarget, components: SurfaceComponent[]) =>
      call(RENDER_SURFACE_TOOL, { target, title: "HTTP methods", components }),
    read: (surfaceId: string) => call(READ_BOARD_SURFACE_TOOL, { surfaceId }),
    remove: (surfaceIds: string[]) =>
      call(DELETE_BOARD_SURFACE_TOOL, { surfaceIds }),
    update: (surfaceId: string, components: SurfaceComponent[]) =>
      call(UPDATE_BOARD_SURFACE_TOOL, {
        surfaceId,
        title: "HTTP methods, revised",
        components,
      }),
  };
};

const surfaceIdOf = (operations: unknown) =>
  (operations as { createSurface: { surfaceId: string } }[])[0]?.createSurface
    .surfaceId;

/** A Board view as `renderSurface` makes it. */
const createBoardSurface = async (): Promise<BoardSurface> =>
  BoardSurfaceResultSchema.parse(
    await createTools().render("canvas", BOARD_TREE),
  ).surface;

describe("renderSurface", () => {
  it("returns a chat surface as an a2ui_operations envelope", async () => {
    const result = await createTools().render("chat", CHAT_TREE);
    const ops = result[A2UI_OPERATIONS_KEY] as Record<string, unknown>[];

    expect(ops[0]).toMatchObject({
      createSurface: { catalogId: CHAT_CATALOG_ID },
    });
    const surfaceId = surfaceIdOf(ops);
    expect(surfaceId?.startsWith(CHAT_SURFACE_ID_PREFIX)).toBe(true);
    expect(ops[1]).toMatchObject({
      updateComponents: { surfaceId, components: CHAT_TREE },
    });
    expect(result.surface).toBeUndefined();
  });

  it("returns a canvas surface as a Board view, without an envelope", async () => {
    const result = await createTools().render("canvas", BOARD_TREE);
    const { surface } = BoardSurfaceResultSchema.parse(result);

    expect(result[A2UI_OPERATIONS_KEY]).toBeUndefined();
    expect(surface.title).toBe("HTTP methods");
    expect(surface.revision).toBe(1);
    expect(surface.id.startsWith(BOARD_SURFACE_ID_PREFIX)).toBe(true);
    expect(surfaceIdOf(surface.operations)).toBe(surface.id);
    expect(surface.operations[0]).toMatchObject({
      createSurface: { catalogId: BOARD_CATALOG_ID },
    });
  });

  it("gives every call its own surface id", async () => {
    const tools = createTools();
    const [a, b] = await Promise.all([
      tools.render("chat", CHAT_TREE),
      tools.render("chat", CHAT_TREE),
    ]);
    expect(surfaceIdOf(a?.[A2UI_OPERATIONS_KEY])).not.toBe(
      surfaceIdOf(b?.[A2UI_OPERATIONS_KEY]),
    );
  });

  it("rejects Board-only components in the chat", async () => {
    const result = await createTools().render("chat", BOARD_TREE);

    expect(result[A2UI_OPERATIONS_KEY]).toBeUndefined();
    expect(result.error).toEqual(expect.stringContaining(SURFACE_ERROR_PREFIX));
    expect(result.error).toEqual(expect.stringContaining("Stack"));
  });

  it("returns the errors for a child that does not exist", async () => {
    const result = await createTools().render("canvas", [
      { id: "root", component: "Stack", children: ["gone"] },
      { id: "tip", component: "Callout", tone: "tip", text: "Orphan" },
    ]);

    expect(result.surface).toBeUndefined();
    expect(result.error).toEqual(expect.stringContaining("gone"));
  });

  it("accepts the Board-only components on the canvas, not in the chat", async () => {
    const tree: SurfaceComponent[] = [
      {
        id: "root",
        component: "Stack",
        children: ["code", "params", "trade", "plan"],
      },
      {
        id: "code",
        component: "CodeBlock",
        language: "typescript",
        filename: "",
        code: "const x = 1;\nconsole.log(x);",
        highlightLines: [2],
      },
      {
        id: "params",
        component: "KeyValueList",
        title: "",
        items: [{ key: "method", value: "GET or POST" }],
      },
      {
        id: "trade",
        component: "ProsCons",
        prosTitle: "Pros",
        pros: ["Simple"],
        consTitle: "Cons",
        cons: ["Verbose"],
      },
      {
        id: "plan",
        component: "Checklist",
        title: "Plan",
        items: [{ text: "Read the notes", done: true }],
      },
    ];
    const tools = createTools();

    expect(
      BoardSurfaceResultSchema.safeParse(await tools.render("canvas", tree))
        .success,
    ).toBe(true);
    expect((await tools.render("chat", tree)).error).toEqual(
      expect.stringContaining("CodeBlock"),
    );
  });

  it("rejects components outside both catalogs", () => {
    expect(
      RenderSurfaceArgsSchema.safeParse({
        target: "canvas",
        title: "x",
        components: [
          { id: "root", component: "Stack", children: ["q"] },
          { id: "q", component: "QuestionCard", question: "?" },
        ],
      }).success,
    ).toBe(false);
  });
});

describe("readBoardSurface", () => {
  it("returns a view's title and components", async () => {
    const surface = await createBoardSurface();
    const result = await createTools([surface]).read(surface.id);

    expect(result).toEqual({
      surfaceId: surface.id,
      title: "HTTP methods",
      components: BOARD_TREE,
    });
  });

  it("lists the Board's views when the id is unknown", async () => {
    const surface = await createBoardSurface();
    const result = await createTools([surface]).read("board-missing");

    expect(result.error).toEqual(
      expect.stringContaining(BOARD_SURFACE_NOT_FOUND),
    );
    expect(result.error).toEqual(expect.stringContaining(surface.id));
  });

  it("says so when the Board is empty", async () => {
    expect(await createTools().read("board-1")).toEqual({
      error: BOARD_EMPTY,
    });
  });
});

describe("updateBoardSurface", () => {
  it("replaces the components, keeping the id and raising the revision", async () => {
    const surface = await createBoardSurface();
    const revised: SurfaceComponent[] = [
      { id: "root", component: "Stack", children: ["cols", "tags"] },
      ...BOARD_TREE.slice(1),
      { id: "tags", component: "TagList", tags: ["REST"] },
    ];

    const result = await createTools([surface]).update(surface.id, revised);
    const updated = BoardSurfaceResultSchema.parse(result).surface;

    expect(updated.id).toBe(surface.id);
    expect(updated.revision).toBe(2);
    expect(updated.title).toBe("HTTP methods, revised");
    expect(surfaceIdOf(updated.operations)).toBe(surface.id);
    expect(updated.operations[1]).toMatchObject({
      updateComponents: { surfaceId: surface.id, components: revised },
    });
  });

  it("returns the errors for an invalid revision and keeps the view", async () => {
    const surface = await createBoardSurface();
    const result = await createTools([surface]).update(surface.id, [
      { id: "root", component: "Stack", children: ["gone"] },
      { id: "tip", component: "Callout", tone: "tip", text: "Orphan" },
    ]);

    expect(result.surface).toBeUndefined();
    expect(result.error).toEqual(expect.stringContaining(SURFACE_ERROR_PREFIX));
  });

  it("never makes a view for an unknown id", async () => {
    const result = await createTools().update("board-missing", BOARD_TREE);

    expect(result).toEqual({ error: BOARD_EMPTY });
  });
});

describe("deleteBoardSurface", () => {
  it("returns the views it removes and skips unknown ids", async () => {
    const [a, b] = await Promise.all([
      createBoardSurface(),
      createBoardSurface(),
    ]);
    const result = await createTools([a, b]).remove([a.id, "board-missing"]);

    expect(result).toEqual({ removed: [{ id: a.id, title: a.title }] });
  });

  it("can clear the whole Board", async () => {
    const [a, b] = await Promise.all([
      createBoardSurface(),
      createBoardSurface(),
    ]);
    const result = await createTools([a, b]).remove([a.id, b.id]);

    expect(result.removed).toHaveLength(2);
  });

  it("removes nothing when no id matches or none is given", async () => {
    const surface = await createBoardSurface();
    const tools = createTools([surface]);

    expect((await tools.remove(["board-missing"])).error).toEqual(
      expect.stringContaining(surface.id),
    );
    expect(await tools.remove([])).toEqual({ error: NO_SURFACE_IDS });
  });
});
