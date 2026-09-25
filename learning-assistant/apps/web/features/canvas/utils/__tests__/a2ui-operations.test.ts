import { describe, expect, it } from "vitest";

import { parseSurfaceOperations } from "@/features/canvas/utils/a2ui-operations";

const create = (surfaceId: string) => ({
  version: "v0.9",
  createSurface: { surfaceId, catalogId: "c" },
});
const components = (surfaceId: string) => ({
  version: "v0.9",
  updateComponents: { surfaceId, components: [] },
});

describe("parseSurfaceOperations", () => {
  it("keeps operations that create and fill the given surface", () => {
    const ops = [create("board-1"), components("board-1")];
    expect(parseSurfaceOperations(ops, "board-1")).toEqual(ops);
  });

  it("rejects operations for another surface", () => {
    expect(
      parseSurfaceOperations(
        [create("board-1"), components("board-2")],
        "board-1",
      ),
    ).toEqual([]);
  });

  it("rejects a list that does not start by creating the surface", () => {
    expect(parseSurfaceOperations([components("board-1")], "board-1")).toEqual(
      [],
    );
  });

  it("rejects unknown versions, kinds and empty lists", () => {
    expect(parseSurfaceOperations([], "s")).toEqual([]);
    expect(
      parseSurfaceOperations([{ ...create("s"), version: "v0.8" }], "s"),
    ).toEqual([]);
    expect(
      parseSurfaceOperations(
        [create("s"), { version: "v0.9", deleteSurface: { surfaceId: "s" } }],
        "s",
      ),
    ).toEqual([]);
  });
});
