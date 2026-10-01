import { initialLearningState } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { toBoardDraft } from "../board-draft";

const ROOT = { id: "root", component: "Stack", children: ["p1", "p2"] };
const PARAGRAPH = { id: "p1", component: "Paragraph", text: "Hello" };

const renderCall = (args: unknown) => ({
  toolCallId: "c1",
  toolCallName: "renderSurface",
  args,
});

describe("toBoardDraft", () => {
  it("drafts a new canvas view from the components written so far", () => {
    const draft = toBoardDraft(
      initialLearningState.board,
      renderCall({
        target: "canvas",
        title: "Overview",
        components: [ROOT, PARAGRAPH, { id: "p2", component: "Parag" }],
      }),
    );

    expect(draft).toMatchObject({ id: "board-draft-c1", title: "Overview" });
    expect(draft?.operations[1]).toMatchObject({
      updateComponents: {
        surfaceId: "board-draft-c1",
        components: [{ ...ROOT, children: ["p1"] }, PARAGRAPH],
      },
    });
  });

  it("waits for the target, the title and the root", () => {
    for (const args of [
      { target: "chat", title: "Card", components: [ROOT] },
      { target: "canvas", title: "", components: [ROOT] },
      { target: "canvas", title: "Overview", components: [PARAGRAPH] },
      "not an object",
      null,
    ]) {
      expect(toBoardDraft([], renderCall(args))).toBeNull();
    }
  });

  it("drafts a revision under the id of the view it revises", () => {
    const board = [
      { id: "board-1", title: "Old", operations: [], revision: 1 },
    ];
    const call = (surfaceId: string) => ({
      toolCallId: "c2",
      toolCallName: "updateBoardSurface",
      args: { surfaceId, title: "Revised", components: [ROOT] },
    });

    expect(toBoardDraft(board, call("board-1"))?.id).toBe("board-1");
    expect(toBoardDraft(board, call("board-"))).toBeNull();
  });
});
