import { describe, expect, it } from "vitest";

import { highlightCode } from "@/features/canvas/utils/highlighter";

describe("highlightCode", () => {
  it("colours code in a known language, one token list per line", async () => {
    const lines = await highlightCode("const a = 1;\nreturn a;", "TypeScript");

    expect(lines).toHaveLength(2);
    expect(lines?.[0]?.map(({ content }) => content).join("")).toBe(
      "const a = 1;",
    );
    const colours = new Set(lines?.flat().map(({ color }) => color));
    expect(colours.size).toBeGreaterThan(1);
  });

  it("accepts language aliases", async () => {
    expect(await highlightCode("print(1)", "py")).not.toBeNull();
  });

  it("returns null for a language it does not know", async () => {
    expect(await highlightCode("x", "not-a-language")).toBeNull();
    expect(await highlightCode("x", "constructor")).toBeNull();
  });
});
