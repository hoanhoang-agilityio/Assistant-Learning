import { describe, expect, it } from "vitest";

import {
  SELECTION_FENCE,
  SIMPLIFY_SELECTION_INTRO,
} from "@/features/canvas/constants/material";
import { formatSimplifySelectionMessage } from "@/features/canvas/utils/material-messages";

describe("formatSimplifySelectionMessage", () => {
  it("fences the selection so it can be passed on exactly", () => {
    const selection = "- line one\n- line two";
    expect(formatSimplifySelectionMessage(selection)).toBe(
      `${SIMPLIFY_SELECTION_INTRO}\n${SELECTION_FENCE}\n${selection}\n${SELECTION_FENCE}`,
    );
  });
});
